"""Testes do `bot/auth`: chat_id, rate limiter, 2-step confirmation."""

from __future__ import annotations

import pytest

from monitoritcd.bot.auth import (
    InvalidConfirmationTokenError,
    RateLimiter,
    RateLimitExceededError,
    TwoStepConfirmation,
    UnauthorizedChatError,
    verify_chat_id,
)


@pytest.mark.unit
class TestVerifyChatID:
    def test_valid_chat_id_passes(self) -> None:
        verify_chat_id(12345, owner_chat_id=12345)

    def test_invalid_chat_id_rejected(self) -> None:
        with pytest.raises(UnauthorizedChatError):
            verify_chat_id(99999, owner_chat_id=12345)

    def test_zero_chat_id_rejected(self) -> None:
        with pytest.raises(UnauthorizedChatError):
            verify_chat_id(0, owner_chat_id=12345)

    def test_negative_owner_chat_id_works(self) -> None:
        # Telegram group/channel chat_ids são negativos
        verify_chat_id(-100123, owner_chat_id=-100123)


@pytest.mark.unit
class TestRateLimiter:
    def test_under_limit_passes(self) -> None:
        rl = RateLimiter(max_per_minute=3)
        rl.check(1, now=0.0)
        rl.check(1, now=1.0)
        rl.check(1, now=2.0)
        # 3 OK; 4ª excede
        with pytest.raises(RateLimitExceededError):
            rl.check(1, now=3.0)

    def test_window_slides(self) -> None:
        rl = RateLimiter(max_per_minute=2)
        rl.check(1, now=0.0)
        rl.check(1, now=1.0)
        # 61s depois, janela rolou; pode novamente
        rl.check(1, now=62.0)

    def test_per_chat_isolation(self) -> None:
        rl = RateLimiter(max_per_minute=1)
        rl.check(chat_id=1, now=0.0)
        # Outro chat_id não é afetado
        rl.check(chat_id=2, now=0.0)
        with pytest.raises(RateLimitExceededError):
            rl.check(chat_id=1, now=0.5)

    def test_default_uses_canonical_limit(self) -> None:
        from monitoritcd.core import limits  # noqa: PLC0415

        rl = RateLimiter()
        for i in range(limits.BOT_COMMANDS_PER_MINUTE):
            rl.check(1, now=float(i))
        with pytest.raises(RateLimitExceededError):
            rl.check(1, now=float(limits.BOT_COMMANDS_PER_MINUTE))


@pytest.mark.unit
class TestTwoStepConfirmation:
    def test_issue_returns_token_string(self) -> None:
        manager = TwoStepConfirmation()
        token = manager.issue("test_action", now=0.0)
        assert isinstance(token, str)
        assert len(token) >= 10

    def test_consume_valid_token(self) -> None:
        manager = TwoStepConfirmation(ttl_seconds=60)
        token = manager.issue("delete:foo", now=0.0)
        manager.consume(token, "delete:foo", now=30.0)

    def test_consume_is_single_use(self) -> None:
        manager = TwoStepConfirmation(ttl_seconds=60)
        token = manager.issue("delete:foo", now=0.0)
        manager.consume(token, "delete:foo", now=10.0)
        with pytest.raises(InvalidConfirmationTokenError):
            manager.consume(token, "delete:foo", now=20.0)

    def test_consume_expired_token(self) -> None:
        manager = TwoStepConfirmation(ttl_seconds=60)
        token = manager.issue("delete:foo", now=0.0)
        with pytest.raises(InvalidConfirmationTokenError):
            manager.consume(token, "delete:foo", now=120.0)

    def test_consume_wrong_action_rejected(self) -> None:
        manager = TwoStepConfirmation()
        token = manager.issue("action:A", now=0.0)
        with pytest.raises(InvalidConfirmationTokenError):
            manager.consume(token, "action:B", now=10.0)

    def test_consume_unknown_token_rejected(self) -> None:
        manager = TwoStepConfirmation()
        with pytest.raises(InvalidConfirmationTokenError):
            manager.consume("not-a-real-token", "any:action")

    def test_two_tokens_different_strings(self) -> None:
        manager = TwoStepConfirmation()
        t1 = manager.issue("a", now=0.0)
        t2 = manager.issue("b", now=0.1)
        assert t1 != t2

    def test_cleanup_removes_expired(self) -> None:
        manager = TwoStepConfirmation(ttl_seconds=60)
        # Emite tokens em t=0; em t=120 ambos expiraram
        manager.issue("a", now=0.0)
        manager.issue("b", now=0.0)
        # Issue novo em t=120 dispara cleanup interno
        manager.issue("c", now=120.0)
        assert len(manager._tokens) == 1
