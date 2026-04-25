"""Cloud Function HTTPS — webhook do bot Telegram.

Substitui o polling worker local (Task Scheduler Windows) por webhook
serverless: bot funciona 24/7 sem PC ligado.

Telegram envia POST com Update payload sempre que o bot recebe mensagem.
Esta função valida o secret token, despacha para os handlers existentes,
e responde 200.

Reutiliza:
- monitoritcd.bot.handlers (BotContext + comandos /observar, /status, etc)
- monitoritcd.bot.poller (handle_update + send_message)
- monitoritcd.storage.firestore_store (storage real)

Princípios canônicos:
- Telegram envia `X-Telegram-Bot-Api-Secret-Token` que deve bater com
  TELEGRAM_WEBHOOK_SECRET. Sem token correto = 401.
- chat_id != owner = ignorar silenciosamente (verify_chat_id no handler).
- Resposta 200 sempre que possível para Telegram não retentar.
- Erros NUNCA vazam para o user — handlers pegam exceções.

Deploy:
    gcloud functions deploy bot_webhook --gen2 --region=southamerica-east1 ...

Configurar webhook no Telegram (uma vez):
    curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
         -d "url=https://bot-webhook-XXX.run.app" \
         -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
"""

from __future__ import annotations

import asyncio
import logging
import os

import functions_framework
import httpx
from flask import Request, Response

from monitoritcd.bot.auth import RateLimiter, TwoStepConfirmation
from monitoritcd.bot.handlers import BotContext
from monitoritcd.bot.poller import handle_update
from monitoritcd.core.config import get_settings
from monitoritcd.storage.firestore_store import FirestoreStorage

logger = logging.getLogger("bot_webhook")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Globais reutilizadas entre invocações (Cloud Run keep-warm reutiliza)
_rate_limiter: RateLimiter | None = None
_settings = None
_storage: FirestoreStorage | None = None
_confirmation: TwoStepConfirmation | None = None


def _ensure_initialized() -> None:
    """Inicializa estado singleton (lazy, primeira invocação)."""
    global _settings, _storage, _rate_limiter, _confirmation  # noqa: PLW0603
    if _settings is None:
        _settings = get_settings()
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    if _confirmation is None:
        _confirmation = TwoStepConfirmation()
    if _storage is None:
        from google.cloud.firestore import AsyncClient  # noqa: PLC0415 - lazy

        client = AsyncClient(project=_settings.FIREBASE_PROJECT_ID)
        _storage = FirestoreStorage(client, _settings.OWNER_ID)


async def _process_update(update: dict) -> None:
    """Wrapper async para chamar handle_update do poller."""
    _ensure_initialized()
    assert _settings is not None
    assert _storage is not None
    assert _rate_limiter is not None
    assert _confirmation is not None

    ctx = BotContext(
        settings=_settings,
        storage=_storage,
        confirmation=_confirmation,
    )
    async with httpx.AsyncClient() as client:
        await handle_update(
            update,
            settings=_settings,
            ctx=ctx,
            rate_limiter=_rate_limiter,
            client=client,
        )


@functions_framework.http
def bot_webhook(request: Request) -> Response:
    """Entry point HTTPS — recebe POST do Telegram."""
    if request.method != "POST":
        return Response("method not allowed", status=405)

    # Auth: X-Telegram-Bot-Api-Secret-Token deve bater com TELEGRAM_WEBHOOK_SECRET
    expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected or received != expected:
        logger.warning("auth failed from %s", request.remote_addr)
        return Response("unauthorized", status=401)

    try:
        update = request.get_json(force=True, silent=True) or {}
    except Exception:
        update = {}

    if not update:
        return Response("no payload", status=200)

    update_id = update.get("update_id", "?")
    logger.info("update_id=%s keys=%s", update_id, list(update.keys()))

    try:
        asyncio.run(_process_update(update))
    except Exception as e:
        logger.exception("update processing failed: %s", type(e).__name__)

    return Response("ok", status=200)
