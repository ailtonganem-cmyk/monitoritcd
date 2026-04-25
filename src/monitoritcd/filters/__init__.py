"""Pipeline de filtros: keywords → prescore → LLM classifier."""

from __future__ import annotations

from monitoritcd.filters.keywords import (
    KEYWORDS_BY_TOPIC,
    KEYWORDS_DEFAULT,
    KEYWORDS_ITCD,
    KEYWORDS_REGIME_BENS,
    KEYWORDS_SUCESSOES,
    detect_topics,
    matches_keywords,
)
from monitoritcd.filters.prescore import prescore

__all__ = [
    "KEYWORDS_BY_TOPIC",
    "KEYWORDS_DEFAULT",
    "KEYWORDS_ITCD",
    "KEYWORDS_REGIME_BENS",
    "KEYWORDS_SUCESSOES",
    "detect_topics",
    "matches_keywords",
    "prescore",
]
