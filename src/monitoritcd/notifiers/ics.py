"""Geração de calendário ICS (#158, #160) com prazos legislativos.

Cobre IDEAS.md #158 (Calendar.ics local) e #160 (subscribable URL pública).

Extrai datas de `Documento.original.data_publicacao` + datas detectáveis
em `metadados_extraidos`. Cada doc com data vira um VEVENT.

Princípios canônicos:
- Princípio 1: campos sanitizados via _ical_escape antes do output
- Princípio 2: limit padrão 100 events para manter ICS leve
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import Documento

DEFAULT_ICS_LIMIT: Final[int] = 100


def _ical_escape(text: str) -> str:
    """Escape ICS conforme RFC 5545: `,;\\\\` precisam ser escapados."""
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _format_dt(dt: datetime) -> str:
    """Formata datetime no formato UTC ICS (YYYYMMDDTHHMMSSZ)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _build_vevent(doc: Documento) -> str | None:
    """Constrói um VEVENT a partir do documento. Retorna None se sem data."""
    dt = doc.original.data_publicacao
    if dt is None:
        return None

    summary = _ical_escape(doc.original.titulo_raw[:200])
    description_parts: list[str] = []
    if doc.llm:
        description_parts.append(doc.llm.resumo)
    description_parts.append(f"Fonte: {doc.source.nome}")
    description_parts.append(f"URL: {doc.original.url}")
    description = _ical_escape("\n".join(description_parts))
    uid = f"{doc.doc_id}@monitoritcd"

    return (
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{_format_dt(datetime.now(UTC))}\r\n"
        f"DTSTART:{_format_dt(dt)}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description}\r\n"
        f"URL:{doc.original.url}\r\n"
        f"CATEGORIES:{_ical_escape(doc.source.uf)}\r\n"
        "END:VEVENT\r\n"
    )


def build_ics(
    docs: Sequence[Documento],
    *,
    calendar_name: str = "MonitorITCD",
    limit: int = DEFAULT_ICS_LIMIT,
) -> str:
    """Constrói calendário ICS RFC 5545.

    Args:
        docs: documentos com data_publicacao.
        calendar_name: nome exibido em apps de calendário.
        limit: máximo de events.
    """
    events = [v for v in (_build_vevent(d) for d in docs[:limit]) if v]
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//MonitorITCD//PT-BR//\r\n"
        f"X-WR-CALNAME:{_ical_escape(calendar_name)}\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n" + "".join(events) + "END:VCALENDAR\r\n"
    )


__all__ = ["DEFAULT_ICS_LIMIT", "build_ics"]
