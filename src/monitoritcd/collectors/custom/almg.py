"""Coletor para Assembleia Legislativa de Minas Gerais (ALMG).

Endpoint público: `https://dadosabertos.almg.gov.br/api/v2/`
Documentação: https://dadosabertos.almg.gov.br/api/ajuda/swagger/view/lastest

Cobre dois caminhos:

1. **Proposições em tramitação** — `/proposicoes/pesquisa/direcionada`
   Projetos de Lei, Propostas de Emenda Constitucional, Mensagens, etc.,
   ainda em fase de tramitação.

2. **Legislação mineira** — `/legislacao/mineira/pesquisa/direcionada`
   Leis, Decretos, Resoluções já sancionados / em vigor.

A API aceita `palavraChave={termo}` para busca textual. Como o domínio
ITCD/Sucessões/Regime de Bens demanda múltiplos termos, o YAML configura
uma lista (`palavras_chave`) e o collector faz N queries com dedup por
`numeroDoc` ou (`tipo`+`numero`+`ano`).

Princípios canônicos aplicados:
1. **MAX_BYTES**: cada resposta JSON limitada por timeout HTTP (30s).
2. **Validação anti-SSRF**: BaseCollector.fetch() valida URL.
3. **Saída pydantic**: ALMG retorna JSON; convertemos para `RawItem` validado.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from monitoritcd.core.base_collector import BaseCollector, CollectorError

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = ("ITCMD", "ITCD", "transmissão causa mortis")
DEFAULT_DIAS_RECENTES = 60
DEFAULT_MAX_PAGINAS = 1  # 20 items/página é suficiente; raramente >20 hits/keyword/mês


# URLs públicas ALMG (não a API): construídas a partir de tipo+numero+ano
ALMG_PUBLIC_BASE = "https://www.almg.gov.br"


class ALMGCollector(BaseCollector):
    """Collector ALMG via API JSON.

    YAML config esperado em `selectors`:
        modo: "proposicoes" | "legislacao"     (obrigatório)
        palavras_chave: [str, ...]              (opcional; default: DEFAULT_KEYWORDS)
        dias: int                                (opcional; default: 60)
    """

    async def collect(self) -> list[RawItem]:
        sel = self.source.selectors or {}
        modo = sel.get("modo", "legislacao")
        if modo not in {"proposicoes", "legislacao"}:
            msg = f"modo ALMG inválido em {self.source.id}: {modo}"
            raise CollectorError(msg)

        # selectors são str-only (Source.selectors: dict[str, str]).
        # Listas/ints serializadas: "kw1|kw2|kw3" e "60".
        palavras_raw = sel.get("palavras_chave") or "|".join(DEFAULT_KEYWORDS)
        palavras = [p.strip() for p in palavras_raw.split("|") if p.strip()]
        if not palavras:
            msg = f"palavras_chave vazia em {self.source.id}"
            raise CollectorError(msg)

        try:
            dias = int(sel.get("dias", str(DEFAULT_DIAS_RECENTES)))
        except (TypeError, ValueError) as e:
            msg = f"dias inválido em {self.source.id}: {e}"
            raise CollectorError(msg) from e

        cutoff = datetime.now(UTC) - timedelta(days=dias)

        # Dedup global por numeroDoc (mesmo doc pode aparecer em múltiplas keywords)
        seen: set[str] = set()
        items: list[RawItem] = []

        for palavra in palavras:
            url = self._build_url(palavra)
            try:
                payload = await self.fetch(url)
            except (CollectorError, httpx.HTTPError) as e:
                # Falha em uma keyword não interrompe as outras — pode ser
                # rate limit, 500 transitório, ou termo com syntax inválida.
                logger.warning(
                    "almg.fetch_failed",
                    source=self.source.id,
                    palavra=palavra,
                    error=str(e),
                )
                continue

            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.warning(
                    "almg.invalid_json",
                    source=self.source.id,
                    palavra=palavra,
                    error=str(e),
                )
                continue

            lista = (data.get("resultado") or {}).get("listaItem") or []
            for raw in lista:
                key = raw.get("numeroDoc") or raw.get("numDoc")
                if not key or key in seen:
                    continue
                seen.add(key)

                item = self._parse_item(raw, modo=modo)
                if item is None:
                    continue
                if item.data_publicacao and item.data_publicacao < cutoff:
                    continue
                items.append(item)

        logger.info(
            "almg.collected",
            source=self.source.id,
            modo=modo,
            count=len(items),
            keywords=len(palavras),
        )
        return items

    def _build_url(self, palavra: str) -> str:
        params = {
            "palavraChave": palavra,
            "formato": "json",
            "ordem": "data_DESC" if "legislacao" in self.source.url else "ano_DESC_numero_DESC",
        }
        return f"{self.source.url}?{urllib.parse.urlencode(params)}"

    def _parse_item(self, raw: dict[str, Any], *, modo: str) -> RawItem | None:
        if modo == "proposicoes":
            return self._parse_proposicao(raw)
        return self._parse_legislacao(raw)

    def _parse_proposicao(self, raw: dict[str, Any]) -> RawItem | None:
        sigla = raw.get("siglaTipoProjeto") or ""
        numero = raw.get("numero") or ""
        ano = raw.get("ano") or ""
        if not (sigla and numero and ano):
            return None

        titulo = raw.get("proposicao") or f"{sigla} {numero}/{ano}"
        assunto = raw.get("assunto") or raw.get("ementa") or ""
        autor = raw.get("autor") or ""
        situacao = raw.get("situacao") or ""

        texto_parts = [
            assunto,
            f"Autor: {autor}" if autor else "",
            f"Situação: {situacao}" if situacao else "",
        ]
        texto = "\n\n".join(p for p in texto_parts if p) or None

        # URL pública canônica (ALMG)
        url = (
            f"{ALMG_PUBLIC_BASE}/atividade-parlamentar/tramitacao-projetos/?"
            f"tipoProjeto={urllib.parse.quote(sigla)}&numProjeto={numero}&ano={ano}"
        )

        data_pub = _parse_iso_date(raw.get("dataPublicacao"))
        numero_doc = raw.get("numeroDoc") or f"{sigla}-{numero}-{ano}"

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=texto,
            data_pub=data_pub,
            content_for_hash=numero_doc,
        )

    def _parse_legislacao(self, raw: dict[str, Any]) -> RawItem | None:
        tipo = raw.get("tipo") or ""
        numero = raw.get("numero") or ""
        ano = raw.get("ano") or ""
        if not (tipo and numero and ano):
            return None

        titulo = raw.get("norma") or f"{tipo} {numero}/{ano}"
        ementa = raw.get("ementa") or ""
        origem = raw.get("origem") or ""
        texto = f"{ementa}\n\nOrigem: {origem}" if origem else ementa or None

        # URL pública: caminho normativo na ALMG
        tipo_path = tipo.lower().replace(" ", "-")
        url = f"{ALMG_PUBLIC_BASE}/legislacao-mineira/{tipo_path}/{numero}/{ano}"

        data_pub = _parse_compact_date(raw.get("data"))
        num_doc = raw.get("numDoc") or f"{tipo}-{numero}-{ano}"

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=texto,
            data_pub=data_pub,
            content_for_hash=num_doc,
        )


def _parse_iso_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        parsed = datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_compact_date(s: str | None) -> datetime | None:
    """Parse YYYYMMDD format used by ALMG legislação."""
    if not s or len(s) != 8 or not s.isdigit():  # noqa: PLR2004 - YYYYMMDD len
        return None
    try:
        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=UTC)
    except ValueError:
        return None
