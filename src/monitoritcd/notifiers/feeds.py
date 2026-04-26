"""Geração de feeds estáticos para auto-hospedagem em GitHub Pages.

Cobre IDEAS.md #153 (RSS), #154 (Atom por UF), #155 (Atom por tipo),
#156 (Atom por relevância), #157 (JSON Feed).

Feeds gerados em `docs/feeds/` são servidos diretamente pelo GitHub Pages
sem custo adicional. Atualizados pelo cron diário (monitor.yml).

Princípios canônicos:
- Princípio 1: dados vêm de Documento (já validado pydantic), `xml.sax.saxutils.escape`
  protege contra XML injection.
- Princípio 2: capa em N items (default 50) para manter feeds pequenos.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final
from xml.sax.saxutils import escape as xml_escape

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import Documento

DEFAULT_FEED_LIMIT: Final[int] = 50
FEED_BASE_URL_DEFAULT: Final[str] = "https://example.github.io/monitoritcd/feeds"


def _isoformat(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(UTC).isoformat()
    return dt.astimezone(UTC).isoformat()


def _atom_entry(doc: Documento) -> str:
    """Constrói uma `<entry>` Atom para um documento."""
    titulo = xml_escape(doc.original.titulo_raw)
    url = xml_escape(doc.original.url)
    resumo = xml_escape(doc.llm.resumo) if doc.llm else ""
    updated = _isoformat(doc.original.data_publicacao or doc.original.fetched_at)
    return (
        f"<entry>"
        f"<title>{titulo}</title>"
        f'<link href="{url}"/>'
        f"<id>{xml_escape(doc.doc_id)}</id>"
        f"<updated>{updated}</updated>"
        f'<summary type="html">{resumo}</summary>'
        f'<category term="{xml_escape(doc.source.uf)}"/>'
        f"</entry>"
    )


def build_atom_feed(
    docs: Sequence[Documento],
    *,
    title: str,
    feed_id: str,
    base_url: str = FEED_BASE_URL_DEFAULT,
    limit: int = DEFAULT_FEED_LIMIT,
) -> str:
    """Constrói feed Atom 1.0 estático.

    Args:
        docs: documentos a incluir.
        title: título do feed.
        feed_id: identificador URI do feed (ex: "monitoritcd:atom:uf:SP").
        base_url: URL base onde o feed estará hospedado.
        limit: máximo de entries.
    """
    entries = "".join(_atom_entry(d) for d in docs[:limit])
    updated = _isoformat(datetime.now(UTC))
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        f"<title>{xml_escape(title)}</title>"
        f"<id>{xml_escape(feed_id)}</id>"
        f"<updated>{updated}</updated>"
        f'<link href="{xml_escape(base_url)}" rel="self"/>'
        f"{entries}"
        "</feed>"
    )


def build_rss_feed(
    docs: Sequence[Documento],
    *,
    title: str,
    base_url: str = FEED_BASE_URL_DEFAULT,
    limit: int = DEFAULT_FEED_LIMIT,
) -> str:
    """#153 — RSS 2.0 estático."""
    items = []
    for d in docs[:limit]:
        titulo = xml_escape(d.original.titulo_raw)
        url = xml_escape(d.original.url)
        resumo = xml_escape(d.llm.resumo) if d.llm else ""
        pub_date = _isoformat(d.original.data_publicacao or d.original.fetched_at)
        items.append(
            f"<item>"
            f"<title>{titulo}</title>"
            f"<link>{url}</link>"
            f"<guid>{xml_escape(d.doc_id)}</guid>"
            f"<description>{resumo}</description>"
            f"<pubDate>{pub_date}</pubDate>"
            f"<category>{xml_escape(d.source.uf)}</category>"
            f"</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0">'
        "<channel>"
        f"<title>{xml_escape(title)}</title>"
        f"<link>{xml_escape(base_url)}</link>"
        f"<description>{xml_escape(title)}</description>" + "".join(items) + "</channel></rss>"
    )


def build_json_feed(
    docs: Sequence[Documento],
    *,
    title: str,
    base_url: str = FEED_BASE_URL_DEFAULT,
    limit: int = DEFAULT_FEED_LIMIT,
) -> str:
    """#157 — JSON Feed v1.1 estático."""
    items = []
    for d in docs[:limit]:
        items.append(
            {
                "id": d.doc_id,
                "url": d.original.url,
                "title": d.original.titulo_raw,
                "content_text": d.llm.resumo if d.llm else "",
                "date_published": _isoformat(d.original.data_publicacao or d.original.fetched_at),
                "tags": [d.source.uf, d.llm.tipo.value] if d.llm else [d.source.uf],
            }
        )
    payload = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": title,
        "home_page_url": base_url,
        "feed_url": f"{base_url}/feed.json",
        "items": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_feeds_per_uf(docs: Sequence[Documento]) -> dict[str, str]:
    """#154 — Atom feed por UF. Retorna dict UF → conteúdo Atom."""
    by_uf: dict[str, list[Documento]] = {}
    for d in docs:
        by_uf.setdefault(d.source.uf, []).append(d)
    return {
        uf: build_atom_feed(items, title=f"MonitorITCD — {uf}", feed_id=f"monitoritcd:atom:uf:{uf}")
        for uf, items in by_uf.items()
    }


def build_feeds_per_tipo(docs: Sequence[Documento]) -> dict[str, str]:
    """#155 — Atom feed por tipo de ato."""
    by_tipo: dict[str, list[Documento]] = {}
    for d in docs:
        if not d.llm:
            continue
        tipo = d.llm.tipo.value
        by_tipo.setdefault(tipo, []).append(d)
    return {
        tipo: build_atom_feed(
            items,
            title=f"MonitorITCD — {tipo}",
            feed_id=f"monitoritcd:atom:tipo:{tipo}",
        )
        for tipo, items in by_tipo.items()
    }


def build_feeds_per_relevancia(
    docs: Sequence[Documento],
    *,
    threshold: int = 7,
) -> str:
    """#156 — Atom feed apenas com relevância ≥ threshold."""
    high_rel = [d for d in docs if d.llm and d.llm.relevancia >= threshold]
    return build_atom_feed(
        high_rel,
        title=f"MonitorITCD — Alta relevância (≥ {threshold})",
        feed_id=f"monitoritcd:atom:relevancia:{threshold}",
    )


__all__ = [
    "DEFAULT_FEED_LIMIT",
    "build_atom_feed",
    "build_feeds_per_relevancia",
    "build_feeds_per_tipo",
    "build_feeds_per_uf",
    "build_json_feed",
    "build_rss_feed",
]
