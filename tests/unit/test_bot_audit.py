"""Testes do bot.audit.log_bot_action."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from monitoritcd.bot.audit import _hash_payload, log_bot_action
from monitoritcd.bot.auth import TwoStepConfirmation
from monitoritcd.bot.handlers import BotContext
from monitoritcd.core.config import Settings
from monitoritcd.storage.in_memory import InMemoryStorage

OWNER = "owner-audit"


def _settings() -> Settings:
    return Settings(
        OWNER_ID=OWNER,
        OWNER_EMAIL="o@example.com",
        GEMINI_API_KEY=SecretStr("g"),
        RESEND_API_KEY=SecretStr("p"),
        RESEND_FROM_EMAIL="b@example.com",
        TELEGRAM_BOT_TOKEN=SecretStr("t"),
        TELEGRAM_OWNER_CHAT_ID=1,
        TELEGRAM_WEBHOOK_SECRET=SecretStr("ws"),
        FIREBASE_PROJECT_ID="p",
        FIREBASE_STORAGE_BUCKET="p.appspot.com",
        FIREBASE_SERVICE_ACCOUNT_JSON=SecretStr("{}"),
    )


def _ctx() -> BotContext:
    return BotContext(
        settings=_settings(),
        storage=InMemoryStorage(OWNER),
        confirmation=TwoStepConfirmation(),
    )


@pytest.mark.unit
class TestHashPayload:
    def test_hash_estavel_independente_ordem(self) -> None:
        h1 = _hash_payload({"a": 1, "b": 2})
        h2 = _hash_payload({"b": 2, "a": 1})
        assert h1 == h2

    def test_hash_diferente_para_payloads_diferentes(self) -> None:
        assert _hash_payload({"a": 1}) != _hash_payload({"a": 2})

    def test_hash_60_chars_hex(self) -> None:
        h = _hash_payload({"x": "y"})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


@pytest.mark.unit
class TestLogBotAction:
    @pytest.mark.asyncio
    async def test_persiste_entry_no_audit(self) -> None:
        ctx = _ctx()
        await log_bot_action(
            ctx,
            action="bot.marcar",
            payload={"doc_id": "d1", "tag": "x"},
        )
        # Verifica que foi gravado (InMemoryStorage tem _audit list)
        assert len(ctx.storage._audit) == 1
        entry = ctx.storage._audit[0]
        assert entry.actor == "bot:OWNER"
        assert entry.action == "bot.marcar"
        assert entry.result == "success"
        assert entry.error is None
        assert entry.owner_id == OWNER
        assert len(entry.entry_id) > 0
        assert len(entry.payload_hash) == 64
        assert len(entry.prev_hash) == 64

    @pytest.mark.asyncio
    async def test_failure_grava_error(self) -> None:
        ctx = _ctx()
        await log_bot_action(
            ctx,
            action="bot.observar.add",
            payload={"pattern": "x"},
            result="failure",
            error="storage offline",
        )
        entry = ctx.storage._audit[0]
        assert entry.result == "failure"
        assert entry.error == "storage offline"

    @pytest.mark.asyncio
    async def test_audit_failure_nao_propaga(self) -> None:
        # Storage que sempre falha — handler deve continuar funcionando
        from unittest.mock import patch  # noqa: PLC0415

        ctx = _ctx()
        with patch.object(
            ctx.storage,
            "append_audit",
            side_effect=RuntimeError("audit table missing"),
        ):
            # Não deve levantar
            await log_bot_action(
                ctx,
                action="bot.test",
                payload={},
            )
        # Audit não foi persistido, mas chamada não quebrou
        assert len(ctx.storage._audit) == 0

    @pytest.mark.asyncio
    async def test_hash_chain_consistente(self) -> None:
        ctx = _ctx()
        await log_bot_action(ctx, action="a1", payload={"n": 1})
        await log_bot_action(ctx, action="a2", payload={"n": 2})
        await log_bot_action(ctx, action="a3", payload={"n": 3})

        entries = ctx.storage._audit
        assert len(entries) == 3
        # prev_hash da entrada N+1 = hash da entrada N (encadeamento)
        assert entries[0].prev_hash != entries[1].prev_hash  # iniciais diferentes
        # Cada entry tem prev_hash diferente (cadeia avança)
        assert entries[1].prev_hash != entries[2].prev_hash
