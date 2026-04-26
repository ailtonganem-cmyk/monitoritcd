"""Resilience primitives (Sugestões #44-#47).

- `circuit_breaker`: silencia automaticamente fontes que falham consecutivamente.
- `keyword_matcher`: matcher otimizado (Aho-Corasick com fallback).
"""

from monitoritcd.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
)
from monitoritcd.resilience.keyword_matcher import KeywordMatcher

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
    "KeywordMatcher",
]
