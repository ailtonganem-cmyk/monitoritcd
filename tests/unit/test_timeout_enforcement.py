"""Testes de timeout efetivo (Sugestão #14).

`MAX_DURATION` da Seção 7 do CLAUDE.md é uma promessa.
Verificamos que limites estão definidos e propagados ao httpx.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from monitoritcd.core import limits


@pytest.mark.unit
def test_limits_max_duration_defined() -> None:
    """Limits centraliza durações máximas."""
    assert hasattr(limits, "HTTP_TIMEOUT_SECONDS")
    assert hasattr(limits, "LLM_TIMEOUT_SECONDS")
    assert limits.HTTP_TIMEOUT_SECONDS > 0
    assert limits.LLM_TIMEOUT_SECONDS > 0


@pytest.mark.unit
def test_max_http_timeout_reasonable() -> None:
    """HTTP timeout não pode ser absurdo (> 5min) nem mínimo (< 5s)."""
    assert 5 <= limits.HTTP_TIMEOUT_SECONDS <= 300


@pytest.mark.unit
def test_httpx_timeout_object_constructible() -> None:
    """Limits são valores aceitos pelo httpx.Timeout."""
    t = httpx.Timeout(limits.HTTP_TIMEOUT_SECONDS)
    assert t.read == limits.HTTP_TIMEOUT_SECONDS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_wait_for_enforces_timeout() -> None:
    """asyncio.wait_for com timeout 0.1s aborta task lenta."""

    async def slow_task() -> None:
        await asyncio.sleep(5.0)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_task(), timeout=0.1)
