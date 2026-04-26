"""Testes do PerCommandRateLimiter (Sugestão #24)."""

from __future__ import annotations

import pytest

from monitoritcd.bot.auth import (
    PER_COMMAND_LIMITS,
    PerCommandRateLimiter,
    RateLimitExceededError,
)


@pytest.mark.unit
def test_estados_command_limited_to_5_per_minute() -> None:
    """Comando mutativo `/estados` é apertado (5/min)."""
    rl = PerCommandRateLimiter()
    chat = 123
    for i in range(5):
        rl.check(chat, "estados", now=i * 0.1)
    with pytest.raises(RateLimitExceededError):
        rl.check(chat, "estados", now=0.6)


@pytest.mark.unit
def test_buscar_command_more_permissive() -> None:
    """Comando read-only `/buscar` permite 30/min."""
    rl = PerCommandRateLimiter()
    chat = 123
    # 30 ok
    for i in range(30):
        rl.check(chat, "buscar", now=i * 0.01)
    # 31 falha
    with pytest.raises(RateLimitExceededError):
        rl.check(chat, "buscar", now=0.4)


@pytest.mark.unit
def test_unknown_command_passes() -> None:
    """Comando sem limite específico não é restringido (cabe ao global)."""
    rl = PerCommandRateLimiter()
    # 100 vezes do mesmo comando desconhecido — não deve falhar aqui
    for i in range(100):
        rl.check(123, "comando_desconhecido", now=i * 0.001)


@pytest.mark.unit
def test_per_chat_isolation() -> None:
    """Limites são por (chat, comando)."""
    rl = PerCommandRateLimiter()
    # Esgota chat 1
    for i in range(5):
        rl.check(1, "estados", now=i * 0.1)
    # Chat 2 ainda está limpo
    rl.check(2, "estados", now=0.5)


@pytest.mark.unit
def test_per_command_isolation() -> None:
    """Esgotar /estados não afeta /buscar."""
    rl = PerCommandRateLimiter()
    for i in range(5):
        rl.check(1, "estados", now=i * 0.1)
    # Estados está esgotado
    with pytest.raises(RateLimitExceededError):
        rl.check(1, "estados", now=0.6)
    # Mas buscar funciona
    rl.check(1, "buscar", now=0.6)


@pytest.mark.unit
def test_window_slides() -> None:
    """Após 60s+ a janela libera."""
    rl = PerCommandRateLimiter()
    for i in range(5):
        rl.check(1, "estados", now=i * 0.1)
    # Avança 61s
    rl.check(1, "estados", now=61.0)


@pytest.mark.unit
def test_known_mutative_commands_in_limits() -> None:
    """Sanity: comandos críticos têm limite apertado (≤ 10/min)."""
    for cmd in ("estados", "silenciar", "confirmar"):
        assert PER_COMMAND_LIMITS[cmd] <= 10
