"""Coletor da Câmara dos Deputados via API de Dados Abertos v2.

API REST oficial: https://dadosabertos.camara.leg.br/api/v2

Cobre proposições federais (PL, PLP, PEC, MPV, etc.) que afetam ITCD em
todos os 27 entes — Reforma Tributária (PEC 45), LC 87/96 modificações,
LCs sobre IBS/ITBI, vetos presidenciais com efeito ITCD.

Endpoint: `/proposicoes?keywords={kw}&itens={n}&pagina={p}`

Resposta JSON:
    {
        "dados": [
            {
                "id": 2613074,
                "uri": "https://dadosabertos.camara.leg.br/api/v2/proposicoes/2613074",
                "siglaTipo": "PLP",
                "codTipo": 140,
                "numero": 86,
                "ano": 2026,
                "ementa": "Altera a Lei Complementar...",
                "dataApresentacao": "2026-04-01T11:03"
            }
        ],
        "links": [{"rel": "self", "href": "..."}, ...]
    }

Princípios canônicos:
- URL externa validada via BaseCollector (anti-SSRF)
- JSON validado com try/except + fallback silencioso
- Falha em uma keyword não derruba as outras
"""

from __future__ import annotations

import json
import urllib.parse
from typing import TYPE_CHECKING, Any

import structlog

from monitoritcd.collectors.custom._common import (
    parse_iso_date,
    parse_keywords_batch_config,
)
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
DEFAULT_DIAS_RECENTES = 365  # 1 ano (proposições federais têm tramitação longa)
DEFAULT_PAGE_SIZE = 50

# URL pública para visualização humana (não a URI da API)
PORTAL_PROPOSICAO = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={}"


class CamaraDeputadosCollector(BaseCollector):
    """Coletor da Câmara dos Deputados via API JSON v2.

    YAML config esperado em `selectors`:
        palavras_chave: "ITCMD|ITCD|sucessão"  (pipe-separated)
        dias: "365"                            (filtro pós-fetch)
        page_size: "50"                        (limite por keyword)
    """

    async def collect(self) -> list[RawItem]:
        cfg = parse_keywords_batch_config(
            self.source,
            default_keywords=DEFAULT_KEYWORDS,
            default_dias=DEFAULT_DIAS_RECENTES,
            default_page_size=DEFAULT_PAGE_SIZE,
        )

        seen: set[int] = set()
        items: list[RawItem] = []

        for palavra in cfg.palavras:
            url = self._build_url(palavra, cfg.page_size)
            try:
                payload = await self.fetch(url)
            except CollectorError as e:
                logger.warning(
                    "camara.fetch_failed",
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
                    "camara.invalid_json",
                    source=self.source.id,
                    palavra=palavra,
                    error=str(e),
                )
                continue

            dados = data.get("dados") or []
            for raw in dados:
                prop_id = raw.get("id")
                if not isinstance(prop_id, int) or prop_id in seen:
                    continue
                seen.add(prop_id)

                item = self._parse_proposicao(raw)
                if item is None:  # pragma: no cover - defesa redundante
                    continue
                if item.data_publicacao and item.data_publicacao < cfg.cutoff:
                    continue
                items.append(item)

        logger.info(
            "camara.collected",
            source=self.source.id,
            count=len(items),
            keywords=len(cfg.palavras),
        )
        return items

    def _build_url(self, palavra: str, page_size: int) -> str:
        params = {
            "keywords": palavra,
            "itens": str(page_size),
            "ordem": "DESC",
            "ordenarPor": "id",
        }
        return f"{self.source.url}?{urllib.parse.urlencode(params)}"

    def _parse_proposicao(self, raw: dict[str, Any]) -> RawItem | None:
        prop_id = raw.get("id")
        if not isinstance(prop_id, int):
            return None

        sigla = (raw.get("siglaTipo") or "PROPOSIÇÃO").strip()
        numero = raw.get("numero", "")
        ano = raw.get("ano", "")
        titulo = f"{sigla} {numero}/{ano}".strip()

        ementa = (raw.get("ementa") or "").strip()
        texto = ementa or None

        url = PORTAL_PROPOSICAO.format(prop_id)
        data_pub = parse_iso_date(raw.get("dataApresentacao"))

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=texto,
            data_pub=data_pub,
            content_for_hash=f"camara:{prop_id}",
        )
