"""Helpers compartilhados entre coletores que fazem batch por keyword.

Coletores que herdam o mesmo padrão (SAPL, ALEP, Câmara, Senado, ALEPE):
- Aceitam `palavras_chave` (pipe-separated) em selectors
- Aceitam `dias` (int) e `page_size` (int) opcionais
- Filtram items por cutoff de data
- Retornam JSON (ou XML) com lista de itens

Este módulo extrai apenas o *parse* de configuração comum. Cada coletor
mantém sua própria lógica de fetch/parse pois as APIs diferem suficientemente
(GET vs POST, paginação, filtro server-side ou local) que abstração mais
ampla seria forçada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from monitoritcd.core.base_collector import CollectorError

if TYPE_CHECKING:
    from monitoritcd.core.models import Source


@dataclass(frozen=True)
class KeywordsBatchConfig:
    """Config padrão para coletores que fazem batch por keyword."""

    palavras: list[str]
    dias: int
    page_size: int
    cutoff: datetime


def parse_keywords_batch_config(
    source: Source,
    *,
    default_keywords: tuple[str, ...],
    default_dias: int,
    default_page_size: int,
    page_size_key: str = "page_size",
) -> KeywordsBatchConfig:
    """Parseia selectors padrão, valida tipos, retorna config validada.

    Levanta `CollectorError` se valores inválidos. Único ponto de
    parse para todos os coletores que seguem o mesmo padrão.
    """
    sel = source.selectors or {}

    palavras_raw = sel.get("palavras_chave") or "|".join(default_keywords)
    palavras = [p.strip() for p in palavras_raw.split("|") if p.strip()]
    if not palavras:
        msg = f"palavras_chave vazia em {source.id}"
        raise CollectorError(msg)

    try:
        dias = int(sel.get("dias", str(default_dias)))
    except (TypeError, ValueError) as e:
        msg = f"dias inválido em {source.id}: {e}"
        raise CollectorError(msg) from e

    try:
        page_size = int(sel.get(page_size_key, str(default_page_size)))
    except (TypeError, ValueError) as e:
        msg = f"{page_size_key} inválido em {source.id}: {e}"
        raise CollectorError(msg) from e

    cutoff = datetime.now(UTC) - timedelta(days=dias)
    return KeywordsBatchConfig(
        palavras=palavras,
        dias=dias,
        page_size=page_size,
        cutoff=cutoff,
    )


def parse_iso_date(s: str | None) -> datetime | None:
    """Parse ISO datetime, retorna None em invalido. Naive recebe UTC."""
    if not s:
        return None
    try:
        parsed = datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
