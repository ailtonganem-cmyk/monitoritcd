"""Coletor do Senado Federal via API de Dados Abertos `/processo`.

A API legacy `/materia/pesquisa/lista` foi depreciada em 2026-02-01 e o
substituto é `/dadosabertos/processo`. Este coletor usa o endpoint novo
e tenta filtrar por `palavraChave` (validação adicional necessária — se
a API ignorar o filtro, o coletor obtém todo o feed e descarta no
filtro de keywords do pipeline).

Endpoint: `https://legis.senado.leg.br/dadosabertos/processo`

Resposta JSON (formato observado em 2026-04-26):
    [
        {
            "identificacao": "VET 8/2026",
            "ementa": "Dispõe sobre...",
            "dataApresentacao": "2026-01-14",
            "tipoDocumento": "Veto",
            "tramitando": true,
            "casaIdentificadora": "SF"
        },
        ...
    ]

Princípios canônicos:
- URL externa validada via BaseCollector (anti-SSRF)
- JSON validado com try/except + fallback silencioso
- Filtro local por keyword se a API ignorar palavraChave
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from monitoritcd.core.base_collector import BaseCollector, CollectorError

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = (
    "ITCMD",
    "ITCD",
    "transmissão causa mortis",
    "herança",
    "sucessão",
)
DEFAULT_DIAS_RECENTES = 365
DEFAULT_PAGE_SIZE = 50

# URL pública para visualização humana (matérias do Senado)
PORTAL_MATERIA = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{}"


class SenadoCollector(BaseCollector):
    """Coletor do Senado Federal via API JSON `/processo`.

    YAML config esperado em `selectors`:
        palavras_chave: "ITCMD|ITCD|sucessão"  (pipe-separated)
        dias: "365"                            (filtro pós-fetch)
        page_size: "50"                        (limite por keyword)
    """

    async def collect(self) -> list[RawItem]:
        sel = self.source.selectors or {}

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

        try:
            page_size = int(sel.get("page_size", str(DEFAULT_PAGE_SIZE)))
        except (TypeError, ValueError) as e:
            msg = f"page_size inválido em {self.source.id}: {e}"
            raise CollectorError(msg) from e

        cutoff = datetime.now(UTC) - timedelta(days=dias)

        seen: set[str] = set()
        items: list[RawItem] = []

        for palavra in palavras:
            url = self._build_url(palavra, page_size)
            try:
                payload = await self.fetch(url)
            except CollectorError as e:
                logger.warning(
                    "senado.fetch_failed",
                    source=self.source.id,
                    palavra=palavra,
                    error_type=type(e).__name__,
                    error=str(e) or "no message",
                )
                continue

            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.warning(
                    "senado.invalid_json",
                    source=self.source.id,
                    palavra=palavra,
                    error=str(e),
                )
                continue

            registros = _extract_records(data)
            palavra_lower = palavra.lower()

            for raw in registros:
                ident = raw.get("identificacao")
                if not isinstance(ident, str) or not ident or ident in seen:
                    continue

                # Filtro local: se API não respeitou palavraChave, descarta aqui.
                ementa = (raw.get("ementa") or "").lower()
                if palavra_lower not in ementa and palavra_lower not in ident.lower():
                    continue

                seen.add(ident)
                item = self._parse_processo(raw)
                if item is None:  # pragma: no cover - defesa redundante
                    continue
                if item.data_publicacao and item.data_publicacao < cutoff:
                    continue
                items.append(item)

        logger.info(
            "senado.collected",
            source=self.source.id,
            count=len(items),
            keywords=len(palavras),
        )
        return items

    def _build_url(self, palavra: str, page_size: int) -> str:
        params = {
            "palavraChave": palavra,
            "limit": str(page_size),
        }
        return f"{self.source.url}?{urllib.parse.urlencode(params)}"

    def _parse_processo(self, raw: dict[str, Any]) -> RawItem | None:
        ident = raw.get("identificacao")
        if not isinstance(ident, str) or not ident:
            return None

        tipo_doc = (raw.get("tipoDocumento") or "Matéria").strip()
        titulo = f"{tipo_doc} {ident}".strip()

        ementa = (raw.get("ementa") or "").strip()
        tramitando = raw.get("tramitando")
        texto_parts = [
            ementa,
            "Em tramitação." if tramitando else "",
        ]
        texto = "\n\n".join(p for p in texto_parts if p) or None

        # URL pública: extrai ID se presente em links HATEOAS, senão usa busca por id
        codigo_materia = raw.get("codigoMateria") or raw.get("idMateria")
        url = (
            PORTAL_MATERIA.format(codigo_materia)
            if codigo_materia
            else f"https://www25.senado.leg.br/web/atividade/materias?p_p_state=normal&busca={urllib.parse.quote(ident)}"
        )

        data_pub = _parse_iso_date(raw.get("dataApresentacao"))

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=texto,
            data_pub=data_pub,
            content_for_hash=f"senado:{ident}",
        )


def _extract_records(data: Any) -> list[dict[str, Any]]:  # noqa: ANN401
    """API pode retornar lista no top-level OU dict {records:[...]} OU {data:[...]}."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("records", "data", "dados", "items", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


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
