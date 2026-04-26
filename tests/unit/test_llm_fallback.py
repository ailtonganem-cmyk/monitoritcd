"""Testes do FallbackLLMProvider — Gemini → Groq em quota error."""

from __future__ import annotations

from typing import Any

import pytest

from monitoritcd.llm.fallback import (
    FallbackLLMProvider,
    LLMProvidersExhaustedError,
    _is_quota_error,
)


class _StubProvider:
    """Provider de teste simples."""

    def __init__(self, name: str, responses: list[Any]) -> None:
        self.name = name
        self._responses = responses
        self._calls = 0

    async def classify_batch(self, items_text: list[str]) -> list[dict[str, Any]]:
        idx = self._calls
        self._calls += 1
        resp = self._responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return resp


@pytest.mark.unit
class TestIsQuotaError:
    def test_resource_exhausted(self) -> None:
        assert _is_quota_error(Exception("RESOURCE_EXHAUSTED quota"))

    def test_429(self) -> None:
        assert _is_quota_error(Exception("HTTP 429 Too Many Requests"))

    def test_quota_msg(self) -> None:
        assert _is_quota_error(Exception("quota exceeded"))

    def test_rate_limit(self) -> None:
        assert _is_quota_error(Exception("rate limit hit"))

    def test_unrelated_error(self) -> None:
        assert not _is_quota_error(Exception("connection refused"))


@pytest.mark.unit
class TestFallbackProvider:
    @pytest.mark.asyncio
    async def test_primary_success_no_fallback(self) -> None:
        primary = _StubProvider("gemini", [[{"tipo": "lei"}]])
        fallback = _StubProvider("groq", [[{"tipo": "DUMMY"}]])
        provider = FallbackLLMProvider(primary, fallback)
        result = await provider.classify_batch(["item1"])
        assert result == [{"tipo": "lei"}]
        assert primary._calls == 1
        assert fallback._calls == 0

    @pytest.mark.asyncio
    async def test_quota_error_falls_back(self) -> None:
        primary = _StubProvider("gemini", [Exception("RESOURCE_EXHAUSTED 429")])
        fallback = _StubProvider("groq", [[{"tipo": "lei"}]])
        provider = FallbackLLMProvider(primary, fallback)
        result = await provider.classify_batch(["item1"])
        assert result == [{"tipo": "lei"}]
        assert primary._calls == 1
        assert fallback._calls == 1

    @pytest.mark.asyncio
    async def test_non_quota_error_propagates(self) -> None:
        primary = _StubProvider("gemini", [Exception("connection refused")])
        fallback = _StubProvider("groq", [[{"tipo": "lei"}]])
        provider = FallbackLLMProvider(primary, fallback)
        with pytest.raises(Exception, match="connection refused"):
            await provider.classify_batch(["item1"])
        assert fallback._calls == 0

    @pytest.mark.asyncio
    async def test_name_includes_both(self) -> None:
        primary = _StubProvider("gemini-2.5-flash", [])
        fallback = _StubProvider("llama-3.3", [])
        provider = FallbackLLMProvider(primary, fallback)
        assert "gemini-2.5-flash" in provider.name
        assert "llama-3.3" in provider.name


@pytest.mark.unit
class TestTier3DeferQuandoAmbosFalham:
    """Cobre LLMProvidersExhaustedError quando Gemini E Groq estão sem quota."""

    @pytest.mark.asyncio
    async def test_ambos_quota_levanta_providers_exhausted(self) -> None:
        # Cenário real do cron 24957305420: Gemini 429 → fallback Groq → Groq 429
        primary = _StubProvider("gemini", [Exception("RESOURCE_EXHAUSTED 429")])
        fallback = _StubProvider("groq", [Exception("HTTP 429 Too Many Requests")])
        provider = FallbackLLMProvider(primary, fallback)
        with pytest.raises(LLMProvidersExhaustedError) as exc_info:
            await provider.classify_batch(["item1"])
        # Mensagem deve identificar AMBOS provedores
        assert "gemini" in str(exc_info.value)
        assert "groq" in str(exc_info.value)
        assert primary._calls == 1
        assert fallback._calls == 1

    @pytest.mark.asyncio
    async def test_fallback_erro_nao_quota_propaga(self) -> None:
        # Se Gemini cair em quota mas Groq cair em erro NÃO-quota (network),
        # o erro do Groq propaga (não é LLMProvidersExhausted).
        primary = _StubProvider("gemini", [Exception("RESOURCE_EXHAUSTED 429")])
        fallback = _StubProvider("groq", [Exception("connection refused")])
        provider = FallbackLLMProvider(primary, fallback)
        with pytest.raises(Exception, match="connection refused"):
            await provider.classify_batch(["item1"])

    def test_providers_exhausted_e_runtime_error(self) -> None:
        # Garante que o orchestrator pode capturar como RuntimeError genérico
        # se quiser, e que herda corretamente.
        assert issubclass(LLMProvidersExhaustedError, RuntimeError)
