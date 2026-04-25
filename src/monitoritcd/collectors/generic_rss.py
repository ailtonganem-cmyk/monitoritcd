"""Coletor genérico para feeds RSS/Atom.

Usa `feedparser` que tolera RSS mal-formado (comum em diários oficiais).
Em caso de feed totalmente quebrado (sem entries E sem bozo recoverável),
levanta `CollectorError` para o orquestrador isolar.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import feedparser
import structlog

from monitoritcd.core.base_collector import BaseCollector, CollectorError

if TYPE_CHECKING:
    from time import struct_time

    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)


class GenericRSSCollector(BaseCollector):
    """Coletor para feeds RSS/Atom.

    O Source.url deve apontar diretamente para o feed.
    Não requer `selectors`.
    """

    async def collect(self) -> list[RawItem]:
        content = await self.fetch()
        feed = feedparser.parse(content)

        # bozo=1 indica parsing imperfeito; aceitamos se há entries.
        if feed.bozo and not feed.entries:
            msg = f"Feed RSS mal-formado e sem entries: {self.source.url}"
            raise CollectorError(msg)

        items: list[RawItem] = []
        for entry in feed.entries:
            try:
                item = self._entry_to_raw(entry)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(
                    "rss.skip_entry",
                    source=self.source.id,
                    error=str(e),
                )
                continue
            items.append(item)

        logger.info(
            "rss.collected",
            source=self.source.id,
            count=len(items),
            bozo=feed.bozo,
        )
        return items

    def _entry_to_raw(self, entry: Any) -> RawItem:  # noqa: ANN401 - feedparser dict-like
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            msg = "Entry sem título ou link"
            raise ValueError(msg)

        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        data_pub = self._struct_time_to_datetime(published_parsed)

        # Texto: feedparser preenche `summary` automaticamente a partir de
        # <description>, <content>, <subtitle>, etc. Não precisamos de fallback.
        texto = entry.get("summary") or entry.get("description")

        # Hash inclui id se houver, senão link+title (estável entre runs).
        entry_id = entry.get("id") or entry.get("guid") or f"{link}|{title}"

        return self.make_raw_item(
            titulo=title,
            url=link,
            texto=texto,
            data_pub=data_pub,
            content_for_hash=entry_id,
        )

    @staticmethod
    def _struct_time_to_datetime(st: struct_time | None) -> datetime | None:
        if st is None:
            return None
        try:
            return datetime(*st[:6], tzinfo=UTC)
        except (TypeError, ValueError, OverflowError):  # pragma: no cover
            # Defensivo: feedparser normaliza struct_times. Cair aqui significa
            # struct_time corrompido (ex: month=13). Não-determinístico de testar.
            return None
