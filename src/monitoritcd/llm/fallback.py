"""Provedor LLM com fallback automático Gemini → Groq.

Usado em produção: tenta Gemini primeiro (2.5 Flash, gratuito até 1500/dia
mas só 15 RPM em rajadas curtas). Em quota error (429), cai para Groq
(llama-3.3-70b-versatile, 30 RPM gratuito, sem limite diário rígido).

Quando AMBOS LLMs falham com quota, levanta `LLMProvidersExhaustedError`
para o orchestrator deferir classificação (não derrubar pipeline).

Mantém a interface `LLMProvider` Protocol — drop-in para classificadores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from monitoritcd.filters.llm_classifier import LLMProvider

logger = structlog.get_logger(__name__)

# Substrings em mensagens de erro que indicam recuperação possível na próxima
# execução: cota esgotada (429/RESOURCE_EXHAUSTED) ou indisponibilidade transiente
# do provedor (503/502/504). Em ambos os casos, deferimos o batch e tentamos de
# novo no próximo run, evitando derrubar o pipeline por instabilidade externa.
_QUOTA_MARKERS = (
    "RESOURCE_EXHAUSTED",
    "429",
    "quota",
    "rate limit",
    "rate_limit",
    # Transient server errors (Gemini 503 visto em prod 2026-04-27 run 25007589463)
    "503",
    "502",
    "504",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
)


class LLMProvidersExhaustedError(RuntimeError):
    """Ambos primary e fallback LLMs estão em quota/rate limit.

    Orchestrator deve capturar e deferir classificação para próxima execução
    (item permanece como `pending` no storage, não como classified).
    """


def _is_quota_error(exc: Exception) -> bool:
    """True se a exceção sugere quota/rate limit excedido."""
    msg = str(exc).lower()
    return any(marker.lower() in msg for marker in _QUOTA_MARKERS)


class CadeiaLLMProvider:
    """Tenta provedores em ordem; 429/5xx de quota passa ao seguinte."""

    def __init__(self, provedores: list[LLMProvider]) -> None:
        if not provedores:
            msg = "cadeia LLM vazia"
            raise ValueError(msg)
        self._provedores = list(provedores)

    @property
    def name(self) -> str:
        return "+".join(p.name for p in self._provedores)

    async def classify_batch(
        self,
        items_text: list[str],
        *,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        ultimo_quota: Exception | None = None
        for provedor in self._provedores:
            try:
                return await provedor.classify_batch(items_text, system_prompt=system_prompt)
            except Exception as exc:
                if not _is_quota_error(exc):
                    raise
                logger.warning(
                    "llm.cadeia_quota_proximo",
                    provedor=provedor.name,
                    error=type(exc).__name__,
                )
                ultimo_quota = exc
        nomes = ",".join(p.name for p in self._provedores)
        raise LLMProvidersExhaustedError(f"Cadeia esgotada: {nomes}") from ultimo_quota


class FallbackLLMProvider:
    """Wrapper que tenta primary, fallback em quota error."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._cadeia = CadeiaLLMProvider([primary, fallback])
        self._primary = primary
        self._fallback = fallback

    @property
    def name(self) -> str:
        # Reportamos o nome do primary (registrado em LLMResult.llm_model);
        # quando fallback é usado, vai aparecer como "<primary>+<fallback>"
        return f"{self._primary.name}+{self._fallback.name}"

    async def classify_batch(
        self,
        items_text: list[str],
        *,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._cadeia.classify_batch(items_text, system_prompt=system_prompt)
