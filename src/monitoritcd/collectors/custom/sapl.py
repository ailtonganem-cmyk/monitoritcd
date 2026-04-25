"""Coletor SAPL — Sistema de Apoio ao Processo Legislativo (Interlegis).

SAPL é a plataforma open-source mantida pelo programa Interlegis (Senado)
para casas legislativas brasileiras. Tem API REST padronizada Django REST
Framework. Cobertura conhecida (2026-04-25):

- Acre (sapl.al.ac.leg.br)
- Alagoas (sapl.al.al.leg.br)
- Ceará (www.al.ce.leg.br/sapl)
- Espírito Santo (www.al.es.leg.br/sapl)
- Goiás (www.al.go.leg.br/sapl)
- Mato Grosso (sapl.al.mt.leg.br)
- Paraíba (sapl.al.pb.leg.br)
- Pernambuco (www.al.pe.leg.br/sapl)
- Piauí (sapl.al.pi.leg.br)
- Rondônia (sapl.al.ro.leg.br)
- Santa Catarina (www.al.sc.leg.br/sapl)

Endpoint: `/api/materia/materialegislativa/?format=json`

Filtro por palavra-chave usa Django field lookup:
    `ementa__icontains=ITCMD` → busca case-insensitive em ementa

Resposta:
    {"pagination": {...}, "results": [{"id":..., "ementa":..., ...}]}

Princípios canônicos:
- URL externa validada via BaseCollector (anti-SSRF)
- JSON validado com try/except + fallback silencioso
- Falha em uma keyword não derruba as outras
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

DEFAULT_KEYWORDS: tuple[str, ...] = ("ITCMD", "ITCD", "transmissão causa mortis")
DEFAULT_DIAS_RECENTES = 365  # 1 ano por default (proposições têm tramitação longa)
DEFAULT_PAGE_SIZE = 50


class SAPLCollector(BaseCollector):
    """Collector SAPL via API JSON Django REST Framework.

    YAML config esperado em `selectors`:
        palavras_chave: "ITCMD|ITCD"           (pipe-separated)
        dias: "365"                              (filtro pós-fetch)
        page_size: "50"                          (limite por keyword)
        portal_base: "https://www.al.{uf}.leg.br"  (opcional; default: deriva da URL)
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
        portal_base = sel.get("portal_base", _derive_portal_base(self.source.url))

        seen: set[int] = set()
        items: list[RawItem] = []

        for palavra in palavras:
            url = self._build_url(palavra, page_size)
            try:
                payload = await self.fetch(url)
            except CollectorError as e:
                logger.warning(
                    "sapl.fetch_failed",
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
                    "sapl.invalid_json",
                    source=self.source.id,
                    palavra=palavra,
                    error=str(e),
                )
                continue

            results = data.get("results") or []
            for raw in results:
                materia_id = raw.get("id")
                if materia_id in seen:
                    continue
                if not isinstance(materia_id, int):
                    continue
                seen.add(materia_id)

                item = self._parse_materia(raw, portal_base=portal_base)
                if item is None:
                    continue
                if item.data_publicacao and item.data_publicacao < cutoff:
                    continue
                items.append(item)

        logger.info(
            "sapl.collected",
            source=self.source.id,
            count=len(items),
            keywords=len(palavras),
        )
        return items

    def _build_url(self, palavra: str, page_size: int) -> str:
        params = {
            "format": "json",
            "ementa__icontains": palavra,
            "page_size": str(page_size),
            "ordering": "-data_apresentacao",
        }
        return f"{self.source.url}?{urllib.parse.urlencode(params)}"

    def _parse_materia(self, raw: dict[str, Any], *, portal_base: str) -> RawItem | None:
        materia_id = raw.get("id")
        if not isinstance(materia_id, int):
            return None

        # Título: usa `__str__` quando disponível (já formatado: "PL nº 49 de 2024")
        titulo = raw.get("__str__") or f"Matéria {materia_id}"
        ementa = raw.get("ementa") or ""
        data_apr = _parse_iso_date(raw.get("data_apresentacao"))

        # URL pública: portal SAPL serve em /materia/{id} ou /sapl/materia/{id}
        link_backend = raw.get("link_detail_backend") or f"/materia/{materia_id}"
        url = f"{portal_base.rstrip('/')}{link_backend}"

        em_tramitacao = raw.get("em_tramitacao")
        texto_parts = [
            ementa,
            "Em tramitação." if em_tramitacao else "",
        ]
        texto = "\n\n".join(p for p in texto_parts if p) or None

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=texto,
            data_pub=data_apr,
            content_for_hash=f"sapl:{self.source.id}:{materia_id}",
        )


def _derive_portal_base(api_url: str) -> str:
    """De /api/... extrai o portal base (até o /sapl ou raiz)."""
    parsed = urllib.parse.urlparse(api_url)
    # Cobre: https://sapl.al.X.leg.br/api/... → https://sapl.al.X.leg.br
    # Cobre: https://www.al.X.leg.br/sapl/api/... → https://www.al.X.leg.br/sapl
    path = parsed.path
    if "/sapl/api/" in path:
        prefix = path.split("/sapl/api/")[0] + "/sapl"
    elif "/api/" in path:
        prefix = path.split("/api/")[0]
    else:
        prefix = ""
    return f"{parsed.scheme}://{parsed.netloc}{prefix}"


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
