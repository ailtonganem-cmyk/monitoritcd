"""Coletor LexML Portal — busca textual em www.lexml.gov.br/busca/search.

A API SRU oficial (`/busca/SRU`) está descontinuada (404 em 2026-04). O
portal de busca em `/busca/search` permanece como fonte primária. Cobre
TODOS os 27 entes federativos via URNs estruturadas no padrão LexML:

    urn:lex:br;{localidade}:{esfera}:{tipo}:{data};{numero}

Exemplo: `urn:lex:br;sao.paulo:estadual:lei:2000-12-28;10705` é a Lei SP
10.705/2000 (que instituiu o ITCMD em SP).

Este coletor:
1. Faz uma query por palavra-chave para cada termo configurado
2. Parseia HTML estruturado (cada resultado é `<div class="docHit">`)
3. Filtra por localidade quando configurada (ex: ["brasil","sao.paulo"])
4. Retorna RawItems com URN como `content_for_hash` (estável)

Princípios canônicos:
- HTML do LexML é entrada não-confiável → parsing via BeautifulSoup com
  recover, sem `eval`/`exec`.
- `MAX_HTML_BYTES` no fetch (BaseCollector) protege contra payload abusivo.
- URNs validadas por regex antes de aceitar.
"""

from __future__ import annotations

import re
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

DEFAULT_KEYWORDS: tuple[str, ...] = ("ITCMD", "ITCD")
DEFAULT_TIPO_DOC = "Legislação"

# Regex URN LexML: urn:lex:br;{localidade}:{esfera}:{tipo}:{data};{numero}
_URN_RE = re.compile(
    r"^urn:lex:br;[a-z][a-z0-9.\-]*:[a-z]+:[a-z][a-z\-]*:\d{4}-\d{2}-\d{2};[\w\-./]+$"
)
_DATE_BR_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_PORTAL_BASE = "https://www.lexml.gov.br"


class LexMLPortalCollector(BaseCollector):
    """Coletor portal LexML via search HTML.

    YAML config esperado em `selectors`:
        palavras_chave: "ITCMD|ITCD|sucessão"   (pipe-separated; opcional)
        tipo_documento: "Legislação"            (default; opcional)
        localidades: "brasil|sao.paulo"         (filtro pós-fetch; opcional)
    """

    async def collect(self) -> list[RawItem]:
        sel = self.source.selectors or {}

        palavras_raw = sel.get("palavras_chave") or "|".join(DEFAULT_KEYWORDS)
        palavras = [p.strip() for p in palavras_raw.split("|") if p.strip()]
        if not palavras:
            msg = f"palavras_chave vazia em {self.source.id}"
            raise CollectorError(msg)

        tipo_doc = sel.get("tipo_documento", DEFAULT_TIPO_DOC)
        localidades_raw = sel.get("localidades", "")
        localidades = (
            {loc.strip().lower() for loc in localidades_raw.split("|") if loc.strip()}
            if localidades_raw
            else set()
        )

        seen: set[str] = set()
        items: list[RawItem] = []

        for palavra in palavras:
            url = self._build_url(palavra, tipo_doc)
            try:
                html = await self.fetch(url)
            except CollectorError as e:
                logger.warning(
                    "lexml.fetch_failed",
                    source=self.source.id,
                    palavra=palavra,
                    error_type=type(e).__name__,
                    error=str(e) or "no message",
                )
                continue

            page_items = self._parse_results(html, localidades_filter=localidades)
            for item in page_items:
                if item.content_hash in seen:
                    continue
                seen.add(item.content_hash)
                items.append(item)

        logger.info(
            "lexml.collected",
            source=self.source.id,
            count=len(items),
            keywords=len(palavras),
        )
        return items

    def _build_url(self, palavra: str, tipo_doc: str) -> str:
        params = {
            "keyword": palavra,
            "f1-tipoDocumento": tipo_doc,
        }
        return f"{self.source.url}?{urllib.parse.urlencode(params)}"

    def _parse_results(self, html: str, *, localidades_filter: set[str]) -> list[RawItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[RawItem] = []
        for hit in soup.find_all("div", class_="docHit"):
            if not isinstance(hit, Tag):  # pragma: no cover - defensive
                continue
            parsed = self._parse_hit(hit)
            if parsed is None:
                continue
            if localidades_filter and parsed["localidade_norm"] not in localidades_filter:
                continue
            items.append(self._make_item(parsed))
        return items

    def _parse_hit(self, hit: Tag) -> dict[str, str] | None:
        """Extrai campos de uma `<div class="docHit">`."""
        fields: dict[str, str] = {}
        title_url = ""

        for row in hit.find_all("tr"):
            if not isinstance(row, Tag):  # pragma: no cover
                continue
            cells = row.find_all("td")
            if len(cells) < 3:  # noqa: PLR2004 - col1+col2+col3 min
                continue
            label_cell = cells[1]
            value_cell = cells[2]
            if not isinstance(label_cell, Tag) or not isinstance(
                value_cell, Tag
            ):  # pragma: no cover
                continue
            label = label_cell.get_text(strip=True).rstrip(":").lower()
            if not label:
                continue
            fields[label] = value_cell.get_text(" ", strip=True)
            # Captura o href do título
            if label == "título" and not title_url:
                anchor = value_cell.find("a", href=True)
                if isinstance(anchor, Tag):
                    href = anchor.get("href", "")
                    if isinstance(href, str):
                        title_url = href

        urn = fields.get("urn", "").strip()
        if not urn or not _URN_RE.match(urn):
            return None

        # Localidade normalizada para filtro
        localidade = fields.get("localidade", "").strip().lower()
        # Normaliza acentuação simples e espaços
        localidade_norm = (
            localidade.replace("ç", "c")
            .replace("ã", "a")
            .replace("á", "a")
            .replace("â", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ô", "o")
            .replace("ú", "u")
            .replace(" ", ".")
            .replace("-", ".")
        )

        # URL canônica
        if title_url:
            url = title_url if title_url.startswith("http") else f"{_PORTAL_BASE}{title_url}"
        else:
            url = f"{_PORTAL_BASE}/urn/{urn}"

        return {
            "urn": urn,
            "titulo": fields.get("título", "").strip() or urn,
            "data": fields.get("data", "").strip(),
            "ementa": fields.get("ementa", "").strip(),
            "localidade": localidade,
            "localidade_norm": localidade_norm,
            "autoridade": fields.get("autoridade", "").strip(),
            "url": url,
        }

    def _make_item(self, parsed: dict[str, str]) -> RawItem:
        texto_parts = [
            parsed.get("ementa", ""),
            f"Localidade: {parsed['localidade']}" if parsed.get("localidade") else "",
            f"Autoridade: {parsed['autoridade']}" if parsed.get("autoridade") else "",
        ]
        texto = "\n\n".join(p for p in texto_parts if p) or None
        return self.make_raw_item(
            titulo=parsed["titulo"],
            url=parsed["url"],
            texto=texto,
            data_pub=_parse_date_br(parsed.get("data", "")),
            content_for_hash=parsed["urn"],
        )


def _parse_date_br(s: str) -> datetime | None:
    """Parse 'DD/MM/YYYY'."""
    m = _DATE_BR_RE.match(s)
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=UTC)
    except ValueError:
        return None
