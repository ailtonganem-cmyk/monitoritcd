"""Coletor para LexML via API SRU (Search/Retrieve via URL).

LexML é a base federal consolidada de atos normativos brasileiros, mantida
pelo Senado Federal. A API SRU é estável e oficial.

Endpoint: `https://www.lexml.gov.br/busca/SRU`
Documentação: https://www.loc.gov/standards/sru/

O Source.url deve apontar para o endpoint SRU; a query CQL é configurada
em `selectors`:
    selectors:
      query: 'ITCMD or ITCD or "causa mortis"'
      max_records: "50"
      record_schema: "dc"  # dc (Dublin Core) ou ainda mais ricos
"""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from bs4 import BeautifulSoup
from bs4.element import Tag

from monitoritcd.core.base_collector import BaseCollector, CollectorError

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

DEFAULT_QUERY = 'ITCMD or ITCD or "causa mortis"'
DEFAULT_MAX_RECORDS = 50
DEFAULT_RECORD_SCHEMA = "dc"


class LexMLCollector(BaseCollector):
    """Coletor LexML via SRU."""

    async def collect(self) -> list[RawItem]:
        sel = self.source.selectors or {}
        query = sel.get("query", DEFAULT_QUERY)

        try:
            max_records = int(sel.get("max_records", str(DEFAULT_MAX_RECORDS)))
        except (TypeError, ValueError) as e:
            msg = f"max_records inválido em {self.source.id}: {e}"
            raise CollectorError(msg) from e

        record_schema = sel.get("record_schema", DEFAULT_RECORD_SCHEMA)

        params = {
            "operation": "searchRetrieve",
            "version": "1.1",
            "query": query,
            "maximumRecords": str(max_records),
            "recordSchema": record_schema,
        }
        url = f"{self.source.url}?{urllib.parse.urlencode(params)}"

        xml = await self.fetch(url)
        items = self._parse_sru(xml)

        logger.info(
            "lexml.collected",
            source=self.source.id,
            count=len(items),
            query=query,
        )
        return items

    def _parse_sru(self, xml: str) -> list[RawItem]:
        soup = BeautifulSoup(xml, "lxml-xml")
        items: list[RawItem] = []

        # Records podem estar em <srw:record> ou <record> dependendo do namespace
        records = soup.find_all("record")
        for record in records:
            if not isinstance(record, Tag):  # pragma: no cover - defensivo
                continue
            item = self._record_to_item(record)
            if item is not None:
                items.append(item)
        return items

    def _record_to_item(self, record: Tag) -> RawItem | None:
        title_text = self._first_text(record, ["title", "dc:title"])
        link_text = self._first_text(record, ["identifier", "dc:identifier"])
        date_text = self._first_text(record, ["date", "dc:date"])
        type_text = self._first_text(record, ["type", "dc:type"])

        if not title_text or not link_text:
            return None

        data_pub = self._parse_date(date_text)

        return self.make_raw_item(
            titulo=title_text,
            url=link_text,
            texto=type_text or None,
            data_pub=data_pub,
            content_for_hash=link_text,  # identifier é estável
        )

    @staticmethod
    def _first_text(record: Tag, names: list[str]) -> str:
        """Retorna texto da primeira tag encontrada entre `names`."""
        for name in names:
            found = record.find(name)
            if found is not None and isinstance(found, Tag):
                text = found.get_text(strip=True)
                if text:
                    return text
        return ""

    @staticmethod
    def _parse_date(date_text: str) -> datetime | None:
        if not date_text:
            return None
        try:
            # LexML normalmente usa ISO 8601 ou só YYYY-MM-DD
            parsed = datetime.fromisoformat(date_text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
