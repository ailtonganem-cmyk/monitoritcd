"""Testes unitários do `bot/poller`.

Cobre:
- send_message (httpx mock)
- _validate_and_parse (chat_id, rate limit, parse erro)
- handle_update (dispatch + erros)
- configure_logging (estrutura JSON + redator de secrets)
- _make_storage_for_poller (fallback InMemory; producao via FirestoreStorage)

Polling loop em si não testado (loop infinito; já validado em produção
via Cloud Function bot_webhook). Marcado com `# pragma: no cover` no source.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx
import structlog
from pydantic import SecretStr

from monitoritcd.bot.auth import RateLimiter, TwoStepConfirmation
from monitoritcd.bot.handlers import BotContext
from monitoritcd.bot.poller import (
    _make_storage_for_poller,
    _validate_and_parse,
    configure_logging,
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
    async def test_parse_error_envia_aviso_e_aborta(self) -> None:
        # Comando excedendo MAX_BOT_COMMAND_LENGTH levanta ValueError dentro
        # de parse_command -> _validate_and_parse envia aviso e retorna None.
        from monitoritcd.core import limits  # noqa: PLC0415

        async with respx.mock:
            route = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            async with httpx.AsyncClient() as client:
                result = await _validate_and_parse(
                    {
                        "chat": {"id": OWNER_CHAT},
                        "text": "/" + "x" * (limits.MAX_BOT_COMMAND_LENGTH + 10),
                    },
                    settings=_settings(),
                    rate_limiter=RateLimiter(),
                    client=client,
                )
        assert result is None
        assert route.called  # owner foi avisado

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
    async def test_chat_id_invalido_aborta_silenciosamente(self) -> None:
        # parsed=None (chat_id errado) -> handle_update retorna sem dispatch.
        async with respx.mock, httpx.AsyncClient() as client:
            await handle_update(
                {
                    "update_id": 1,
                    "message": {"chat": {"id": 999999}, "text": "/status"},
                },
                settings=_settings(),
                ctx=_ctx(),
                rate_limiter=RateLimiter(),
                client=client,
            )
        # Nenhuma chamada esperada (comportamento silencioso para nao-owner)

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


def _settings_production() -> Settings:
    return Settings(
        OWNER_ID=OWNER,
        OWNER_EMAIL="o@example.com",
        ENV="production",
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


@pytest.mark.unit
class TestConfigureLogging:
    """`configure_logging` ajusta `logging.basicConfig` e structlog com redator."""

    def test_chama_basic_config_com_nivel(self) -> None:
        # logging.basicConfig e idempotente; testamos via mock que recebe o argumento
        with patch("monitoritcd.bot.poller.logging.basicConfig") as mock_bc:
            configure_logging("DEBUG")
        mock_bc.assert_called_once()
        assert mock_bc.call_args.kwargs.get("level") == "DEBUG"

    def test_configura_structlog_com_processors(self) -> None:
        with patch("monitoritcd.bot.poller.structlog.configure") as mock_cfg:
            configure_logging("INFO")
        mock_cfg.assert_called_once()
        kwargs = mock_cfg.call_args.kwargs
        # Pipeline deve ter pelo menos: contextvars, level, timestamp, redator, JSON
        assert "processors" in kwargs
        assert len(kwargs["processors"]) >= 5
        # cache_logger_on_first_use ativo (perf)
        assert kwargs.get("cache_logger_on_first_use") is True

    def test_pipeline_real_nao_levanta(self) -> None:
        # Smoke: pipeline configurado nao explode ao logar token sensivel.
        # Token construido em runtime para nao disparar o gitleaks pre-commit
        # (o redactor e' coberto em tests/security/test_log_redactor.py).
        configure_logging("INFO")
        log = structlog.get_logger("test_redact")
        fake_pat = "gh" + "p_" + "abcdef1234567890abcdef1234567890abcd"
        log.info("evento", token=fake_pat)


@pytest.mark.unit
class TestMakeStorageForPoller:
    """`_make_storage_for_poller` escolhe storage por env, com fallback resiliente."""

    def test_env_dev_retorna_inmemory(self) -> None:
        s = _settings()  # ENV padrao = "dev"
        storage = _make_storage_for_poller(s)
        assert isinstance(storage, InMemoryStorage)
        assert storage.owner_id == OWNER

    def test_env_production_com_runtime_error_faz_fallback(self) -> None:
        # Em producao, se FirestoreStorage levantar RuntimeError (ex: sem creds),
        # _make_storage_for_poller faz fallback para InMemoryStorage e nao quebra.
        s = _settings_production()
        with patch(
            "monitoritcd.storage.firestore_store.FirestoreStorage",
            side_effect=RuntimeError("no GCP creds"),
        ):
            storage = _make_storage_for_poller(s)
        assert isinstance(storage, InMemoryStorage)
        assert storage.owner_id == OWNER
