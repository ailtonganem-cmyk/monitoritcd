"""Coletor ALEP — Assembleia Legislativa do Paraná.

API REST pública em `webservices.assembleia.pr.leg.br/api/public`.

Endpoints relevantes:
    POST /proposicao/filtrar — busca por palavraChave (suporta ITCMD)
    GET  /proposicao/campos  — lista tipos/situações disponíveis

Resposta wrapper Java/Spring:
    {
      "sucesso": true,
      "lista": [
        {"codigo": int, "numero": int, "ano": int, "autor": str,
         "ementa": str, "tipoProposicao": str, "status": str,
         "dataRecebimento": iso, ...}
      ]
    }

Diferente do SAPL e ALMG: aceita POST com JSON body (não query params).
HTTP only — HTTPS retorna 500 (servidor proxy ALEP com SSL handshake quebrado).
URL listada em `HTTP_ALLOWED_HOSTS` em `security/url_validator.py`.

Princípios canônicos:
- HTTP é exceção auditada para este host específico (zero risco de leak
  de credenciais, conteúdo público).
- Resposta JSON validada com try/except.
- Falha em uma keyword não derruba as outras.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from monitoritcd.collectors.custom._common import parse_keywords_batch_config
from monitoritcd.core.base_collector import BaseCollector, CollectorError

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = ("ITCMD", "ITCD", "transmissão causa mortis")
DEFAULT_DIAS_RECENTES = 365
DEFAULT_QUANTIDADE = 50

ALEP_PORTAL_BASE = "https://www.assembleia.pr.leg.br"


class ALEPCollector(BaseCollector):
    """Collector ALEP via API JSON (POST /proposicao/filtrar)."""

    async def collect(self) -> list[RawItem]:
        cfg = parse_keywords_batch_config(
            self.source,
            default_keywords=DEFAULT_KEYWORDS,
            default_dias=DEFAULT_DIAS_RECENTES,
            default_page_size=DEFAULT_QUANTIDADE,
            page_size_key="quantidade",
        )

        seen: set[int] = set()
        items: list[RawItem] = []

        for palavra in cfg.palavras:
            try:
                lista = await self._post_filtrar(palavra, cfg.page_size)
            except (CollectorError, httpx.HTTPError) as e:
                logger.warning(
                    "alep.fetch_failed",
                    source=self.source.id,
                    palavra=palavra,
                    error_type=type(e).__name__,
                    error=str(e) or "no message",
                )
                continue

            for raw in lista:
                codigo = raw.get("codigo")
                if not isinstance(codigo, int) or codigo in seen:
                    continue
                seen.add(codigo)

                item = self._parse_proposicao(raw)
                if item is None:  # pragma: no cover - defesa redundante (codigo ja validado acima)
                    continue
                if item.data_publicacao and item.data_publicacao < cfg.cutoff:
                    continue
                items.append(item)

        logger.info(
            "alep.collected",
            source=self.source.id,
            count=len(items),
            keywords=len(cfg.palavras),
        )
        return items

    async def _post_filtrar(self, palavra: str, quantidade: int) -> list[dict[str, Any]]:
        """POST /proposicao/filtrar — retorna `lista` ou levanta CollectorError."""
        from monitoritcd.core import limits  # noqa: PLC0415
        from monitoritcd.security.url_validator import validate_url  # noqa: PLC0415

        if self._client is None:  # pragma: no cover - defensive
            msg = "client não inicializado"
            raise CollectorError(msg)

        validate_url(self.source.url)
        body = {"palavraChave": palavra, "quantidade": quantidade}
        try:
            response = await self._client.post(
                self.source.url,
                json=body,
                timeout=httpx.Timeout(limits.HTTP_TIMEOUT_SECONDS),
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            msg = f"alep post falhou: {type(e).__name__}"
            raise CollectorError(msg) from e

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            msg = f"alep json inválido: {e}"
            raise CollectorError(msg) from e

        if not data.get("sucesso", False):
            msg = f"alep retornou sucesso=false: {data.get('erro')}"
            raise CollectorError(msg)

        lista = data.get("lista") or []
        return list(lista) if isinstance(lista, list) else []

    def _parse_proposicao(self, raw: dict[str, Any]) -> RawItem | None:
        codigo = raw.get("codigo")
        if not isinstance(codigo, int):
            return None

        numero = raw.get("numero", "")
        ano = raw.get("ano", "")
        tipo = (raw.get("tipoProposicao") or "PROPOSIÇÃO").strip()

        titulo = f"{tipo} {numero}/{ano}".strip()
        ementa = (raw.get("ementa") or "").strip()
        autor = (raw.get("autor") or "").strip()
        status = (raw.get("status") or "").strip()
        local = (raw.get("localAtual") or "").strip()

        texto_parts = [
            ementa,
            f"Autor: {autor}" if autor else "",
            f"Status: {status}" if status else "",
            f"Local atual: {local}" if local else "",
        ]
        texto = "\n\n".join(p for p in texto_parts if p) or None

        # URL pública: portal alep usa codigoProposicao como query
        url = f"{ALEP_PORTAL_BASE}/proposicao?id={codigo}"

        data_pub = _parse_iso_date(raw.get("dataRecebimento"))

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=texto,
            data_pub=data_pub,
            content_for_hash=f"alep:{codigo}",
        )


_TZ_OFFSET_LEN = 5  # comprimento de "+0000" ou "-0300"


def _parse_iso_date(s: str | None) -> datetime | None:
    if not s:
        return None
    # ALEP retorna "2006-06-01T07:00:00.000+0000" — Python aceita com hífen
    try:
        # Normaliza "+0000" para "+00:00" para fromisoformat
        normalized = s
        if len(s) >= _TZ_OFFSET_LEN and s[-_TZ_OFFSET_LEN] in ("+", "-"):
            normalized = s[:-_TZ_OFFSET_LEN] + s[-_TZ_OFFSET_LEN:-2] + ":" + s[-2:]
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
