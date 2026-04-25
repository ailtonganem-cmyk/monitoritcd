"""Polling worker para o bot Telegram.

Alternativa ao webhook (que exigiria Cloud Function deployada). Para uso
single-user e MVP, polling é mais simples e portátil:
- Roda como processo em foreground ou background.
- Consulta `getUpdates` em long-poll de 30s.
- Despacha comandos para handlers em `bot/handlers.py`.
- Envia respostas via `sendMessage`.

Uso:
    python -m monitoritcd.bot.poller

    # Em background (Linux/macOS):
    nohup python -m monitoritcd.bot.poller > bot.log 2>&1 &

Princípios canônicos aplicados:
- `verify_chat_id` rejeita qualquer mensagem que não seja do dono.
- Rate limit por chat_id (mesmo para o dono).
- input_limits via `parse_command`.
- Erros internos não vazam para o user (mensagem genérica).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from monitoritcd.bot.auth import (
    BotAuthError,
    RateLimiter,
    TwoStepConfirmation,
    UnauthorizedChatError,
    verify_chat_id,
)
from monitoritcd.bot.handlers import (
    BotContext,
    dispatch,
    parse_command,
)
from monitoritcd.core import limits
from monitoritcd.core.config import get_settings
from monitoritcd.security.log_redactor import redact_sensitive
from monitoritcd.security.markdown_escape import (
    escape_markdown_v2,
    split_for_telegram,
)
from monitoritcd.storage.in_memory import InMemoryStorage

if TYPE_CHECKING:
    from monitoritcd.core.config import Settings

logger = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org"
LONG_POLL_TIMEOUT = 30  # seconds — Telegram wait time
HTTP_TIMEOUT = LONG_POLL_TIMEOUT + 10  # buffer
MAX_TEXT_LENGTH = 4000  # safety margin abaixo do MAX_TELEGRAM_MSG_BYTES


def configure_logging(level: str = "INFO") -> None:
    """Configura logging JSON com redator de secrets."""
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        cache_logger_on_first_use=True,
    )


async def send_message(
    client: httpx.AsyncClient,
    settings: Settings,
    chat_id: int,
    text: str,
    *,
    parse_mode: str = "MarkdownV2",
) -> None:
    """Envia mensagem via Bot API. Faz split se exceder MAX_TELEGRAM_MSG_BYTES."""
    token = settings.TELEGRAM_BOT_TOKEN.get_secret_value()
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    chunks = split_for_telegram(text, max_bytes=limits.MAX_TELEGRAM_MSG_BYTES)
    for chunk in chunks:
        try:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=httpx.Timeout(15.0),
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.exception("bot.send_failed", chat_id=chat_id, error=str(e))


async def _validate_and_parse(
    msg: dict[str, Any],
    *,
    settings: Settings,
    rate_limiter: RateLimiter,
    client: httpx.AsyncClient,
) -> tuple[int, Any] | None:
    """Valida chat_id, rate limit e parseia comando.

    Returns:
        (chat_id, ParsedCommand) se OK; None se deve abortar (com side effects).
    """
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "")
    if chat_id is None:
        return None

    log = logger.bind(chat_id=chat_id)

    # 1. Validar identidade (princípio 1: backend nunca confia)
    try:
        verify_chat_id(chat_id, owner_chat_id=settings.TELEGRAM_OWNER_CHAT_ID)
    except UnauthorizedChatError:
        log.warning("bot.unauthorized", text=text[:50])
        return None

    # 2. Rate limit
    try:
        rate_limiter.check(chat_id)
    except BotAuthError as e:
        log.warning("bot.rate_limited", error=str(e))
        await send_message(
            client,
            settings,
            chat_id,
            escape_markdown_v2("Rate limit excedido. Aguarde alguns segundos."),
        )
        return None

    # 3. Parse
    try:
        cmd = parse_command(text)
    except ValueError as e:
        log.info("bot.invalid_command", error=str(e))
        await send_message(
            client,
            settings,
            chat_id,
            escape_markdown_v2(f"Comando inválido: {e}"),
        )
        return None

    if cmd is None:
        log.debug("bot.non_command", text=text[:50])
        return None
    return chat_id, cmd


async def handle_update(
    update: dict[str, Any],
    *,
    settings: Settings,
    ctx: BotContext,
    rate_limiter: RateLimiter,
    client: httpx.AsyncClient,
) -> None:
    """Processa um update do Telegram."""
    msg = update.get("message")
    if not msg:
        return  # ignora callbacks, edits, etc. no MVP

    parsed = await _validate_and_parse(
        msg,
        settings=settings,
        rate_limiter=rate_limiter,
        client=client,
    )
    if parsed is None:
        return
    chat_id, cmd = parsed
    log = logger.bind(chat_id=chat_id)

    # Dispatch
    try:
        result = await dispatch(ctx, cmd)
    except Exception as e:  # last-resort: handler erros não vazam pro user
        log.exception("bot.handler_error", command=cmd.name, error=str(e))
        await send_message(
            client,
            settings,
            chat_id,
            escape_markdown_v2("Erro interno ao processar comando."),
        )
        return

    # Enviar resposta (escape pra MarkdownV2)
    await send_message(client, settings, chat_id, escape_markdown_v2(result.text))
    log.info("bot.dispatched", command=cmd.name, is_error=result.is_error)


async def poll_loop(
    settings: Settings,
    ctx: BotContext,
    *,
    stop_event: asyncio.Event,
) -> None:
    """Loop principal de long-polling."""
    token = settings.TELEGRAM_BOT_TOKEN.get_secret_value()
    base_url = f"{TELEGRAM_API}/bot{token}"
    rate_limiter = RateLimiter()
    offset: int | None = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT)) as client:
        # Limpa updates pendentes (resgata só os mais recentes)
        try:
            r = await client.get(f"{base_url}/getUpdates", params={"offset": -1, "limit": 1})
            data = r.json()
            if data.get("ok") and data.get("result"):
                offset = data["result"][-1]["update_id"] + 1
        except (httpx.HTTPError, ValueError):
            pass

        logger.info("bot.poller.start", offset=offset)

        while not stop_event.is_set():
            try:
                params: dict[str, Any] = {
                    "timeout": LONG_POLL_TIMEOUT,
                    "limit": 100,
                    "allowed_updates": ["message"],
                }
                if offset is not None:
                    params["offset"] = offset

                r = await client.get(f"{base_url}/getUpdates", params=params)
                data = r.json()

                if not data.get("ok"):
                    logger.warning("bot.poller.error", response=data)
                    await asyncio.sleep(5)
                    continue

                updates = data.get("result", [])
                for upd in updates:
                    offset = upd["update_id"] + 1
                    await handle_update(
                        upd,
                        settings=settings,
                        ctx=ctx,
                        rate_limiter=rate_limiter,
                        client=client,
                    )
            except asyncio.CancelledError:
                raise
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("bot.poller.network_error", error=str(e))
                await asyncio.sleep(5)
            except Exception as e:
                logger.exception("bot.poller.unexpected_error", error=str(e))
                await asyncio.sleep(5)

        logger.info("bot.poller.stop")


def _make_storage_for_poller(settings: Settings) -> Any:  # noqa: ANN401
    """Storage para o bot. InMemory por padrão; FirestoreStorage se ENV=production."""
    if settings.ENV == "production":
        try:
            from google.cloud.firestore import AsyncClient  # noqa: PLC0415

            from monitoritcd.storage.firestore_store import FirestoreStorage  # noqa: PLC0415

            return FirestoreStorage(
                AsyncClient(project=settings.FIREBASE_PROJECT_ID),
                settings.OWNER_ID,
            )
        except (ImportError, RuntimeError) as e:
            logger.warning("bot.poller.fallback_inmemory", reason=str(e))
    return InMemoryStorage(settings.OWNER_ID)


async def main_async() -> int:
    """Entry async do poller."""
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    storage = _make_storage_for_poller(settings)
    ctx = BotContext(
        settings=settings,
        storage=storage,
        confirmation=TwoStepConfirmation(),
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()

    def _stop_handler() -> None:
        logger.info("bot.poller.shutdown_signal")
        stop_event.set()

    # SIGINT/SIGTERM em Linux; em Windows, KeyboardInterrupt já é tratado
    if sys.platform != "win32":
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                loop.add_signal_handler(sig, _stop_handler)

    with contextlib.suppress(KeyboardInterrupt):
        await poll_loop(settings, ctx, stop_event=stop_event)
    return 0


def main() -> int:
    """Entry sync (chamado por `python -m monitoritcd.bot.poller`)."""
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
