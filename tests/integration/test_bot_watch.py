"""Testes de integração do handler /observar (watch list)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from monitoritcd.bot.auth import TwoStepConfirmation
from monitoritcd.bot.handlers import (
    BotContext,
    ParsedCommand,
    handle_observar,
)
from monitoritcd.core.config import Settings
from monitoritcd.storage import InMemoryStorage

NOW = datetime(2026, 4, 25, tzinfo=UTC)
OWNER = "owner-test"


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


async def _ctx() -> BotContext:
    return BotContext(
        settings=_settings(),
        storage=InMemoryStorage(OWNER),
        confirmation=TwoStepConfirmation(),
    )


@pytest.mark.integration
class TestObservarListar:
    @pytest.mark.asyncio
    async def test_listar_vazio(self) -> None:
        ctx = await _ctx()
        result = await handle_observar(ctx, ParsedCommand(name="observar", args=["listar"]))
        assert "Nenhum watch" in result.text


@pytest.mark.integration
class TestObservarAdicionar:
    @pytest.mark.asyncio
    async def test_sem_args(self) -> None:
        ctx = await _ctx()
        result = await handle_observar(ctx, ParsedCommand(name="observar", args=[]))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_termo_curto_rejeitado(self) -> None:
        ctx = await _ctx()
        # Single arg "ab" -> implicit add path -> pattern "ab" (2 chars) < MIN_PATTERN_LENGTH
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["ab"]),
        )
        assert result.is_error
        assert "curto" in result.text.lower()

    @pytest.mark.asyncio
    async def test_adicionar_e_listar(self) -> None:
        ctx = await _ctx()
        # Cria watch via comando direto (sem subcomando — o termo é o argumento)
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["holding", "familiar", "SP"]),
        )
        assert not result.is_error
        assert "Watch criado" in result.text

        # Lista deve ter 1
        listar = await handle_observar(ctx, ParsedCommand(name="observar", args=["listar"]))
        assert "1 watch" in listar.text


@pytest.mark.integration
class TestObservarRemover:
    @pytest.mark.asyncio
    async def test_remover_id_inexistente(self) -> None:
        ctx = await _ctx()
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["remover", "abc123"]),
        )
        assert result.is_error
        assert "não encontrado" in result.text

    @pytest.mark.asyncio
    async def test_adicionar_e_remover(self) -> None:
        ctx = await _ctx()
        # Adiciona
        await handle_observar(ctx, ParsedCommand(name="observar", args=["ITCMD"]))
        # Pega ID
        watches = await ctx.storage.list_watches()
        assert len(watches) == 1
        wid_prefix = watches[0].watch_id[:8]
        # Remove
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["remover", wid_prefix]),
        )
        assert "removido" in result.text.lower()
        # Lista deve ser zero
        watches_after = await ctx.storage.list_watches()
        assert watches_after == []

    @pytest.mark.asyncio
    async def test_remover_sem_id(self) -> None:
        ctx = await _ctx()
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["remover"]),
        )
        assert result.is_error
