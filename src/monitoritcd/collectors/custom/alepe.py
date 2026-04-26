"""Coletor ALEPE — Assembleia Legislativa de Pernambuco.

Portal de Dados Abertos com endpoints XML (apesar do `?formato=json`,
sempre retorna XML — quirk da API ALEPE).

Endpoint principal:
    GET /api/v1/proposicoes/{tipo}?ano={ano}

Tipos suportados:
    projetos, indicacoes, requerimentos

Resposta XML:
    <projetos>
      <projeto docid="..." numero="..." ano="..." tipo="..."
               ementa="..." dataPublicacao="DD/MM/YYYY">
        <autores>
          <autor nome="..." tipo="DEPUTADO"/>
        </autores>
      </projeto>
    </projetos>

Filtragem por palavra-chave: feita LOCAL (servidor não filtra).
ALEPE retorna ~300-1000 projetos/ano; parsing local é viável.

Princípios canônicos:
- XML parsed via BeautifulSoup com lxml (rápido, robusto)
- Failure em uma keyword/ano não afeta os demais
- Dedup por docid
"""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from bs4 import BeautifulSoup
from bs4.element import Tag

from monitoritcd.core.base_collector import BaseCollector, CollectorError

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = ("ITCMD", "ITCD", "transmissão causa mortis")
DEFAULT_DIAS_RECENTES = 365
DEFAULT_TIPOS = "projetos"

ALEPE_PORTAL_BASE = "https://www.alepe.pe.gov.br"


class ALEPECollector(BaseCollector):
    """Collector ALEPE via API XML por tipo/ano."""

    async def collect(self) -> list[RawItem]:
        sel = self.source.selectors or {}
        palavras_raw = sel.get("palavras_chave") or "|".join(DEFAULT_KEYWORDS)
        palavras = [p.strip().lower() for p in palavras_raw.split("|") if p.strip()]
        if not palavras:
            msg = f"palavras_chave vazia em {self.source.id}"
            raise CollectorError(msg)

        try:
            dias = int(sel.get("dias", str(DEFAULT_DIAS_RECENTES)))
        except (TypeError, ValueError) as e:
            msg = f"dias inválido em {self.source.id}: {e}"
            raise CollectorError(msg) from e

        tipos_raw = sel.get("tipos", DEFAULT_TIPOS)
        tipos = [t.strip() for t in tipos_raw.split("|") if t.strip()]

        cutoff = datetime.now(UTC) - timedelta(days=dias)
        # ALEPE listagem é por ano — busca ano corrente e anterior
        anos = [datetime.now(UTC).year, datetime.now(UTC).year - 1]

        seen: set[str] = set()
        items: list[RawItem] = []

        for tipo in tipos:
            for ano in anos:
                url = f"{self.source.url.rstrip('/')}/{tipo}?{urllib.parse.urlencode({'ano': ano})}"
                try:
                    xml = await self.fetch(url)
                except CollectorError as e:
                    logger.warning(
                        "alepe.fetch_failed",
                        source=self.source.id,
                        tipo=tipo,
                        ano=ano,
                        error_type=type(e).__name__,
                    )
                    continue

                page_items = self._parse_xml(xml, palavras, cutoff, seen)
                items.extend(page_items)

        logger.info(
            "alepe.collected",
            source=self.source.id,
            count=len(items),
            keywords=len(palavras),
            tipos=len(tipos),
        )
        return items

    def _parse_xml(
        self,
        xml: str,
        palavras: list[str],
        cutoff: datetime,
        seen: set[str],
    ) -> list[RawItem]:
        soup = BeautifulSoup(xml, "lxml-xml")
        items: list[RawItem] = []
        for proj in soup.find_all("projeto"):
            if not isinstance(proj, Tag):  # pragma: no cover - defensive
                continue
            docid_raw = proj.get("docid")
            if not isinstance(docid_raw, str) or not docid_raw or docid_raw in seen:
                continue
            docid: str = docid_raw

            ementa_raw = proj.get("ementa") or ""
            ementa: str = ementa_raw if isinstance(ementa_raw, str) else ""
            ementa_lower = ementa.lower()

            # Filtro local por palavra-chave (ALEPE não filtra no servidor)
            if not any(p in ementa_lower for p in palavras):
                continue

            data_pub = _parse_date_br(proj.get("dataPublicacao"))
            if data_pub and data_pub < cutoff:
                continue

            seen.add(docid)
            items.append(self._make_item(proj, ementa, data_pub, docid))
        return items

    def _make_item(
        self,
        proj: Tag,
        ementa: str,
        data_pub: datetime | None,
        docid: str,
    ) -> RawItem:
        numero = proj.get("numero", "") or ""
        ano = proj.get("ano", "") or ""
        tipo = proj.get("tipo", "") or "PROPOSIÇÃO"
        # Bs4 garante str em get() para XML; casts defensivos cobrem
        # malformed input que nao ocorre na pratica.
        if not isinstance(numero, str):  # pragma: no cover
            numero = ""
        if not isinstance(ano, str):  # pragma: no cover
            ano = ""
        if not isinstance(tipo, str):  # pragma: no cover
            tipo = "PROPOSIÇÃO"

        titulo = f"{tipo} {numero}/{ano}".strip()

        autores = []
        for a in proj.find_all("autor"):
            if isinstance(a, Tag):  # pragma: no cover - find_all sempre Tag em XML
                nome = a.get("nome", "")
                if isinstance(nome, str) and nome:
                    autores.append(nome)
        autores_str = ", ".join(autores) if autores else ""

        texto_parts = [
            ementa,
            f"Autores: {autores_str}" if autores_str else "",
        ]
        texto = "\n\n".join(p for p in texto_parts if p) or None

        url = f"{ALEPE_PORTAL_BASE}/proposicoes/{docid}"

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=texto,
            data_pub=data_pub,
            content_for_hash=f"alepe:{docid}",
        )


def _parse_date_br(s: str | None) -> datetime | None:
    """Parse 'DD/MM/YYYY'."""
    if not s or not isinstance(s, str):
        return None
    try:
        d, m, y = s.split("/")
        return datetime(int(y), int(m), int(d), tzinfo=UTC)
    except (ValueError, AttributeError):
        return None
