"""Coletor para SEFAZ-SP (Secretaria da Fazenda de São Paulo).

Endpoint: `https://legislacao.fazenda.sp.gov.br/_api/Web/Lists(guid'...')/Items`

A SEFAZ-SP usa SharePoint Online para hospedar `legislacao.fazenda.sp.gov.br`.
A renderização HTML depende de JavaScript (sem conteúdo no HTML estático), mas
o SharePoint expõe **API REST nativa** em `/_api/web/lists` que retorna JSON
estruturado — caminho oficial e estável.

A lista canônica é "Páginas" (~27 mil itens), com cada ato (Portaria, Comunicado,
RC — Resposta a Consulta, Decisão Normativa, etc.) representado como um item
com campos:
- `PesqLegisTitle`: título canônico ("Portaria SRE 19 de 2026")
- `Ementa`: descrição completa (HTML escapado)
- `DataAto`: data do ato
- `DataPublicacao`: data de publicação no DOE
- `Modified`: última edição (ordenamos por aqui)
- `File/ServerRelativeUrl`: caminho da página `.aspx` final

A API tem limites de filtragem servidor-side em campos `Calculated`/`Note`,
então a estratégia é: pegar os N mais recentes por `Modified desc` e filtrar
por keywords no cliente (igual aos collectors SAPL/Câmara).

Princípios canônicos aplicados:
1. **MAX_BYTES**: cada chamada retorna ~5 MB para top=100; HTTP timeout 30s.
2. **Validação anti-SSRF**: BaseCollector.fetch valida URL.
3. **Saída pydantic**: JSON validado em `RawItem` típico.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime  # noqa: TC003 — usado em runtime via type hints
from typing import TYPE_CHECKING, Any, Self

import httpx
import structlog

from monitoritcd.collectors.custom._common import (
    parse_iso_date,
    parse_keywords_batch_config,
)
from monitoritcd.core import limits
from monitoritcd.core.base_collector import USER_AGENT, BaseCollector, CollectorError

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = (
    "ITCMD",
    "ITCD",
    "causa mortis",
    "transmissão",
    "doação",
)
DEFAULT_DIAS_RECENTES = 60
DEFAULT_TOP = 100  # SharePoint default cap; documentado no portal
MAX_TOP = 500

SEFAZ_SP_BASE = "https://legislacao.fazenda.sp.gov.br"

# SharePoint OData v3 verbose retorna JSON com `{"d":{"results":[...]}}`.
# Sem este Accept, o servidor responde XML Atom (default) ou OData v4 minimal,
# que tem schema diferente. Forçamos verbose para parsing previsível.
SHAREPOINT_ACCEPT = "application/json;odata=verbose"

_TAG_RE = re.compile(r"<[^>]+>")


class SefazSPCollector(BaseCollector):
    """Collector SEFAZ-SP via API SharePoint REST.

    YAML config esperado em `selectors`:
        list_guid: "f286d0d1-5624-47da-a856-a8571296eb7f"  (obrigatório)
        palavras_chave: "ITCMD|ITCD|..."                   (opcional)
        dias: int                                           (opcional; default: 60)
        top: int                                            (opcional; default: 100)
    """

    async def __aenter__(self) -> Self:
        """Override: força Accept SharePoint OData v3 verbose.

        Sem este header o servidor retorna XML Atom (default) ou OData v4
        minimal, ambos com schema diferente do que `_parse_item` espera.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(limits.HTTP_TIMEOUT_SECONDS),
                headers={"User-Agent": USER_AGENT, "Accept": SHAREPOINT_ACCEPT},
                follow_redirects=True,
                max_redirects=5,
            )
        return self

    async def collect(self) -> list[RawItem]:
        sel = self.source.selectors or {}
        list_guid = (sel.get("list_guid") or "").strip()
        if not list_guid:
            msg = f"selectors.list_guid obrigatório em {self.source.id}"
            raise CollectorError(msg)

        cfg = parse_keywords_batch_config(
            self.source,
            default_keywords=DEFAULT_KEYWORDS,
            default_dias=DEFAULT_DIAS_RECENTES,
            default_page_size=DEFAULT_TOP,
            page_size_key="top",
        )

        top = cfg.page_size or DEFAULT_TOP
        if top <= 0 or top > MAX_TOP:
            msg = f"top fora do intervalo (1..{MAX_TOP}) em {self.source.id}: {top}"
            raise CollectorError(msg)

        url = self._build_url(list_guid, top)
        try:
            payload = await self.fetch(url)
        except (CollectorError, httpx.HTTPError) as e:
            logger.warning(
                "sefaz_sp.fetch_failed",
                source=self.source.id,
                error_type=type(e).__name__,
                error=str(e) or "no message",
            )
            return []

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.warning(
                "sefaz_sp.invalid_json",
                source=self.source.id,
                error=str(e),
            )
            return []

        results = (data.get("d") or {}).get("results") or []
        if not isinstance(results, list):
            logger.warning("sefaz_sp.unexpected_payload", source=self.source.id)
            return []

        # Filtragem cliente-side (SharePoint não filtra Note/Calculated)
        palavras_lower = [p.lower() for p in cfg.palavras]

        items: list[RawItem] = []
        for raw in results:
            item = self._parse_item(raw, palavras_lower=palavras_lower, cutoff=cfg.cutoff)
            if item is not None:
                items.append(item)

        logger.info(
            "sefaz_sp.collected",
            source=self.source.id,
            count=len(items),
            top=top,
            keywords=len(cfg.palavras),
        )
        return items

    def _build_url(self, list_guid: str, top: int) -> str:
        """Monta URL OData com $expand=File para incluir ServerRelativeUrl."""
        select = ",".join(
            (
                "ID",
                "Modified",
                "DataAto",
                "DataPublicacao",
                "PesqLegisTitle",
                "Ementa",
                "File/ServerRelativeUrl",
                "File/Name",
            )
        )
        params = {
            "$top": str(top),
            "$orderby": "Modified desc",
            "$expand": "File",
            "$select": select,
        }
        # SharePoint exige `$` literal — encode tudo via urlencode com safe='$'
        qs = urllib.parse.urlencode(params, safe="$/")
        return f"{SEFAZ_SP_BASE}/_api/Web/Lists(guid'{list_guid}')/Items?{qs}"

    def _parse_item(
        self,
        raw: dict[str, Any],
        *,
        palavras_lower: list[str],
        cutoff: datetime,
    ) -> RawItem | None:
        titulo = (raw.get("PesqLegisTitle") or raw.get("Title") or "").strip()
        ementa_html = raw.get("Ementa") or ""
        ementa_text = _TAG_RE.sub(" ", ementa_html).strip() if ementa_html else ""

        if not titulo:
            return None

        # Filtro cliente-side por keyword (case-insensitive, em titulo + ementa)
        haystack = f"{titulo} {ementa_text}".lower()
        if not any(p in haystack for p in palavras_lower):
            return None

        data_ato = parse_iso_date(raw.get("DataAto"))
        data_pub = parse_iso_date(raw.get("DataPublicacao")) or data_ato
        modified = parse_iso_date(raw.get("Modified"))

        # Janela: se temos qualquer data, respeita cutoff. Sem data, mantém
        # (item recém-modificado sem DataAto pode ser republicação válida).
        if data_pub is not None and data_pub < cutoff and (modified is None or modified < cutoff):
            return None

        # URL canônica do ato: File.ServerRelativeUrl é o caminho /Paginas/...aspx
        file_obj = raw.get("File") or {}
        server_rel = file_obj.get("ServerRelativeUrl") or ""
        if not server_rel:
            # Sem URL não tem como o LLM/usuário acessar — descarta
            return None
        url = f"{SEFAZ_SP_BASE}{server_rel}"

        # ID estável para hash (mesmo doc com Modified novo gera content_hash igual,
        # garantindo dedup persistente entre execuções).
        content_id = f"sefaz-sp:{raw.get('ID')}"

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=ementa_text or None,
            data_pub=data_pub,
            content_for_hash=content_id,
        )
