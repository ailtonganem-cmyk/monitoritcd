"""Pré-score heurístico antes do LLM.

Reduz drasticamente o uso de quota do LLM (Gemini Flash: 1.500 req/dia).
Itens com score ≥ `cutoff` (default 0.3) seguem para classificação LLM.
Demais são marcados como descartados sem custo.

Componentes (cada ∈ [0, 1]):
- `density`:    densidade de keywords no texto.
- `authority`:  confiança da fonte (oficial > especializado > genérico).
- `freshness`:  proximidade da data de publicação.

Score final = `0.4 * density + 0.4 * authority + 0.2 * freshness`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from monitoritcd.core.models import TipoFonte

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem, Source

# Pesos da combinação linear
W_DENSITY: Final[float] = 0.4
W_AUTHORITY: Final[float] = 0.4
W_FRESHNESS: Final[float] = 0.2

# Mínimos
MIN_FRESHNESS_SCORE: Final[float] = 0.3
MAX_FRESHNESS_AGE_DAYS: Final[int] = 30
DEFAULT_FRESHNESS_NO_DATE: Final[float] = 0.6  # neutro quando data não disponível

# Cutoff default para passar pro LLM
DEFAULT_CUTOFF: Final[float] = 0.3


def _density_score(text: str, matched_keywords: list[str]) -> float:
    """Densidade: nº de keywords encontradas / 50 palavras (saturado em 1.0)."""
    if not text or not matched_keywords:
        return 0.0
    word_count = max(1, len(text.split()))
    # Normalizado: 1 keyword a cada ~50 palavras = 1.0
    return min(len(matched_keywords) * 50.0 / word_count, 1.0)


def _authority_score(source: Source) -> float:
    """Score baseado em flags da fonte (`trusted`, `tipo`).

    - `trusted=True`        → 1.0  (fonte oficial canônica: LexML, STF, STJ, SEFAZs).
    - SEFAZ/Assembleia/DOE  → 0.7  (oficiais não marcados como trusted).
    - Jurisprudência        → 0.6  (alta confiança, mas pode ser ementa de blog).
    - Doutrina/Notícia      → 0.4  (especializado mas não oficial).
    """
    if source.trusted:
        return 1.0

    high = {TipoFonte.SEFAZ, TipoFonte.ASSEMBLEIA, TipoFonte.DOE}
    if source.tipo in high:
        return 0.7
    if source.tipo == TipoFonte.JURISPRUDENCIA:
        return 0.6
    return 0.4


def _freshness_score(data_pub: datetime | None) -> float:
    """Score por idade. ≤ 0d = 1.0, ≥ 30d = 0.3, sem data = 0.6 (neutro)."""
    if data_pub is None:
        return DEFAULT_FRESHNESS_NO_DATE

    now = datetime.now(UTC)
    if data_pub.tzinfo is None:
        data_pub = data_pub.replace(tzinfo=UTC)

    age_days = max(0, (now - data_pub).days)
    if age_days >= MAX_FRESHNESS_AGE_DAYS:
        return MIN_FRESHNESS_SCORE
    return max(MIN_FRESHNESS_SCORE, 1.0 - age_days / MAX_FRESHNESS_AGE_DAYS)


def prescore(
    item: RawItem,
    source: Source,
    matched_keywords: list[str],
) -> float:
    """Score 0-1 combinando density, authority e freshness.

    Args:
        item: RawItem coletado.
        source: configuração da fonte.
        matched_keywords: keywords encontradas em `item` (do filtro 1).

    Returns:
        Score float em [0.0, 1.0].
    """
    text = (item.titulo_raw or "") + " " + (item.texto_raw or "")
    d = _density_score(text, matched_keywords)
    a = _authority_score(source)
    f = _freshness_score(item.data_publicacao)
    return W_DENSITY * d + W_AUTHORITY * a + W_FRESHNESS * f


def passes_cutoff(score: float, cutoff: float = DEFAULT_CUTOFF) -> bool:
    """Helper: retorna True se score ≥ cutoff."""
    return score >= cutoff
