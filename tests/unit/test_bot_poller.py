"""Testes unitários do `bot/poller`.

Cobre:
- send_message (httpx mock)
- _validate_and_parse (chat_id, rate limit, parse erro)
- handle_update (dispatch + erros)

Polling loop em si não testado (loop infinito; já validado em produção
via Cloud Function bot_webhook).
"""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import SecretStr

from monitoritcd.bot.auth import RateLimiter, TwoStepConfirmation
from monitoritcd.bot.handlers import BotContext
from monitoritcd.bot.poller import (
    _validate_and_parse,
    handle_update,
    send_message,
)
from monitoritcd.core.config import Settings
from monitoritcd.storage.in_memory import InMemoryStorage

OWNER = "owner-test"
OWNER_CHAT = 12345
TOKEN = "111:fake-token-abcdef"  # noqa: S105 - test fixture


def _settings() -> Settings:
    return Settings(
        OWNER_ID=OWNER,
        OWNER_EMAIL="o@example.com",
        GEMINI_API_KEY=SecretStr("g"),
        GMAIL_USER="b@example.com",
        GMAIL_APP_PASSWORD=SecretStr("p"),
        TELEGRAM_BOT_TOKEN=SecretStr(TOKEN),
        TELEGRAM_OWNER_CHAT_ID=OWNER_CHAT,
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
class TestSendMessage:
    @pytest.mark.asyncio
    async def test_envia_mensagem_simples(self) -> None:
        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            async with httpx.AsyncClient() as client:
                await send_message(client, _settings(), OWNER_CHAT, "olá")

    @pytest.mark.asyncio
    async def test_split_quando_grande(self) -> None:
        # Mensagem maior que MAX_TELEGRAM_MSG_BYTES → múltiplas chamadas
        big_msg = "a" * 5000
        async with respx.mock:
            route = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            async with httpx.AsyncClient() as client:
                await send_message(client, _settings(), OWNER_CHAT, big_msg)
            assert route.call_count >= 2

    @pytest.mark.asyncio
    async def test_http_error_loga_e_continua(self) -> None:
        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(500),
            )
            async with httpx.AsyncClient() as client:
                # Não deve levantar
                await send_message(client, _settings(), OWNER_CHAT, "x")


@pytest.mark.unit
class TestValidateAndParse:
    @pytest.mark.asyncio
    async def test_chat_id_invalido_ignora(self) -> None:
        async with respx.mock, httpx.AsyncClient() as client:
            result = await _validate_and_parse(
                {"chat": {"id": 99999}, "text": "/status"},
                settings=_settings(),
                rate_limiter=RateLimiter(),
                client=client,
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_sem_chat_id_ignora(self) -> None:
        async with respx.mock, httpx.AsyncClient() as client:
            result = await _validate_and_parse(
                {"text": "/status"},
                settings=_settings(),
                rate_limiter=RateLimiter(),
                client=client,
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_comando_valido_owner(self) -> None:
        async with respx.mock, httpx.AsyncClient() as client:
            result = await _validate_and_parse(
                {"chat": {"id": OWNER_CHAT}, "text": "/status"},
                settings=_settings(),
                rate_limiter=RateLimiter(),
                client=client,
            )
        assert result is not None
        chat_id, cmd = result
        assert chat_id == OWNER_CHAT
        assert cmd.name == "status"

    @pytest.mark.asyncio
    async def test_nao_eh_comando_ignora(self) -> None:
        async with respx.mock, httpx.AsyncClient() as client:
            result = await _validate_and_parse(
                {"chat": {"id": OWNER_CHAT}, "text": "ola, bot"},
                settings=_settings(),
                rate_limiter=RateLimiter(),
                client=client,
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_rate_limit_envia_aviso(self) -> None:
        rl = RateLimiter()
        # Esgota rate limit
        for _ in range(15):
            try:
                rl.check(OWNER_CHAT)
            except Exception:
                break
        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            async with httpx.AsyncClient() as client:
                result = await _validate_and_parse(
                    {"chat": {"id": OWNER_CHAT}, "text": "/status"},
                    settings=_settings(),
                    rate_limiter=rl,
                    client=client,
                )
        assert result is None


@pytest.mark.unit
class TestHandleUpdate:
    @pytest.mark.asyncio
    async def test_status_dispatch(self) -> None:
        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            async with httpx.AsyncClient() as client:
                await handle_update(
                    {
                        "update_id": 1,
                        "message": {"chat": {"id": OWNER_CHAT}, "text": "/status"},
                    },
                    settings=_settings(),
                    ctx=_ctx(),
                    rate_limiter=RateLimiter(),
                    client=client,
                )

    @pytest.mark.asyncio
    async def test_sem_message_ignora(self) -> None:
        async with httpx.AsyncClient() as client:
            await handle_update(
                {"update_id": 1, "edited_message": {}},
                settings=_settings(),
                ctx=_ctx(),
                rate_limiter=RateLimiter(),
                client=client,
            )

    @pytest.mark.asyncio
    async def test_handler_exception_envia_msg_generica(self) -> None:
        from unittest.mock import patch  # noqa: PLC0415

        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            with patch(
                "monitoritcd.bot.poller.dispatch",
                side_effect=RuntimeError("boom"),
            ):
                async with httpx.AsyncClient() as client:
                    await handle_update(
                        {
                            "update_id": 1,
                            "message": {"chat": {"id": OWNER_CHAT}, "text": "/status"},
                        },
                        settings=_settings(),
                        ctx=_ctx(),
                        rate_limiter=RateLimiter(),
                        client=client,
                    )
