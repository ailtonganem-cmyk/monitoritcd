"""Coletor genérico HTML usando selectors CSS declarativos.

Os `selectors` no Source YAML devem ter:
- `item`: selector CSS que retorna a lista de items.
- `titulo`: selector relativo ao item para o título.
- `link`: selector + atributo (`h3 a@href`) para a URL.
- `data` (opcional): selector para data de publicação.

Exemplo:
    selectors:
      item: "div.lista-atos > article"
      titulo: "h3 a"
      link: "h3 a@href"
      data: "span.data"
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin

import structlog
from bs4 import BeautifulSoup
from bs4.element import Tag

from monitoritcd.core.base_collector import BaseCollector, CollectorError

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

REQUIRED_SELECTORS = frozenset({"item", "titulo", "link"})


class GenericHTMLCollector(BaseCollector):
    """Coletor HTML configurável via selectors CSS."""

    async def collect(self) -> list[RawItem]:
        if not self.source.selectors:
            msg = f"HTML collector requer `selectors`: {self.source.id}"
            raise CollectorError(msg)

        missing = REQUIRED_SELECTORS - set(self.source.selectors)
        if missing:
            msg = f"selectors obrigatórios ausentes em {self.source.id}: {sorted(missing)}"
            raise CollectorError(msg)

        content = await self.fetch()
        soup = BeautifulSoup(content, "lxml")

        items: list[RawItem] = []
        for elem in soup.select(self.source.selectors["item"]):
            if not isinstance(
                elem, Tag
            ):  # pragma: no cover - defensivo, soup.select sempre retorna Tag
                continue
            raw_item = self._extract_item(elem)
            if raw_item is not None:
                items.append(raw_item)

        logger.info("html.collected", source=self.source.id, count=len(items))
        return items

    def _extract_item(self, elem: Tag) -> RawItem | None:
        sel = self.source.selectors or {}

        titulo = self._extract_text(elem, sel["titulo"])
        link_raw = self._extract_attr(elem, sel["link"])

        if not titulo or not link_raw:
            return None

        # URLs relativas → resolver contra a URL da fonte
        link = urljoin(self.source.url, link_raw)

        # V12 (Pentest): rejeita schemes não-HTTPS após resolução
        # (urljoin pode preservar javascript:, data:, file: se o input tinha)
        if not link.lower().startswith(("https://", "http://")):
            return None

        return self.make_raw_item(
            titulo=titulo,
            url=link,
        )

    @staticmethod
    def _extract_text(elem: Tag, selector: str) -> str:
        found = elem.select_one(selector)
        return found.get_text(strip=True) if found else ""

    @staticmethod
    def _extract_attr(elem: Tag, selector_attr: str) -> str:
        """Extrai atributo (`h3 a@href`) ou texto (`h3 a`).

        Sintaxe `selector@attr` segue convenção do `pyquery`/`scrapy`.
        """
        if "@" not in selector_attr:
            found = elem.select_one(selector_attr)
            return found.get_text(strip=True) if found else ""

        sel, attr = selector_attr.rsplit("@", 1)
        found = elem.select_one(sel)
        if found is None:
            return ""
        value = found.get(attr)
        if isinstance(value, list):  # pragma: no cover - multi-valued attrs raros em HTML real
            value = value[0] if value else ""
        return str(value).strip() if value else ""
