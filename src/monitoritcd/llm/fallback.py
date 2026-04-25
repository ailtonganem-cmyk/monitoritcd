"""Provedor LLM com fallback automático Gemini → Groq.

Usado em produção: tenta Gemini primeiro (2.5 Flash, gratuito até 1500/dia
mas só 15 RPM em rajadas curtas). Em quota error (429), cai para Groq
(llama-3.3-70b-versatile, 30 RPM gratuito, sem limite diário rígido).

Mantém a interface `LLMProvider` Protocol — drop-in para classificadores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from monitoritcd.filters.llm_classifier import LLMProvider

logger = structlog.get_logger(__name__)

# Substrings em mensagens de erro que indicam quota esgotada
_QUOTA_MARKERS = (
    "RESOURCE_EXHAUSTED",
    "429",
    "quota",
    "rate limit",
    "rate_limit",
)


def _is_quota_error(exc: Exception) -> bool:
    """True se a exceção sugere quota/rate limit excedido."""
    msg = str(exc).lower()
    return any(marker.lower() in msg for marker in _QUOTA_MARKERS)


class FallbackLLMProvider:
    """Wrapper que tenta primary, fallback em quota error."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        # Reportamos o nome do primary (registrado em LLMResult.llm_model);
        # quando fallback é usado, vai aparecer como "<primary>+<fallback>"
        return f"{self._primary.name}+{self._fallback.name}"

    async def classify_batch(self, items_text: list[str]) -> list[dict[str, Any]]:
        try:
            return await self._primary.classify_batch(items_text)
        except Exception as e:
            if not _is_quota_error(e):
                raise
            logger.warning(
                "llm.primary_quota_exceeded_falling_back",
                primary=self._primary.name,
                fallback=self._fallback.name,
                error=type(e).__name__,
            )
            return await self._fallback.classify_batch(items_text)
