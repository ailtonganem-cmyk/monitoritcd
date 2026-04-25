"""Testes do TelegramNotifier (httpx mockado via respx)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import SecretStr

from monitoritcd.core.config import Settings
from monitoritcd.core.models import (
    Documento,
    LLMResult,
    Parser,
    RawItem,
    SeverityTier,
    Source,
    StatusDocumento,
    TipoAto,
    TipoFonte,
)
from monitoritcd.notifiers.telegram_notifier import TelegramNotifier

FIXED_NOW = datetime(2026, 4, 24, tzinfo=UTC)
TOKEN = "1234567890:fakeFAKE_token_abc"  # noqa: S105 - test fixture
CHAT_ID = 123456


def _settings() -> Settings:
    return Settings(
        OWNER_ID="o",
        OWNER_EMAIL="owner@example.com",
        GEMINI_API_KEY=SecretStr("g"),
        GMAIL_USER="b@example.com",
        GMAIL_APP_PASSWORD=SecretStr("p"),
        TELEGRAM_BOT_TOKEN=SecretStr(TOKEN),
        TELEGRAM_OWNER_CHAT_ID=CHAT_ID,
        TELEGRAM_WEBHOOK_SECRET=SecretStr("ws"),
        FIREBASE_PROJECT_ID="p",
        FIREBASE_STORAGE_BUCKET="p.appspot.com",
        FIREBASE_SERVICE_ACCOUNT_JSON=SecretStr("{}"),
    )


def _doc() -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw="PL 1234/2026 — ITCMD (SP)",
        url="https://x.gov.br/i",
        fetched_at=FIXED_NOW,
        content_hash="a" * 64,
    )
    src = Source(
        id="src",
        uf="SP",
        nome="x",
        tipo=TipoFonte.SEFAZ,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = LLMResult(
        classified_at=FIXED_NOW,
        llm_model="x",
        llm_prompt_version="v1",
        tipo=TipoAto.PROJETO_LEI,
        relevancia=8,
        severity_tier=SeverityTier.ALTA,
        resumo="Resumo factual.",
    )
    return Documento(
        owner_id="o",
        doc_id="d",
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )


@pytest.mark.unit
class TestTelegramNotifier:
    @pytest.mark.asyncio
    async def test_send_message_posts_to_bot_api(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            ).mock(return_value=httpx.Response(200, json={"ok": True}))

            async with TelegramNotifier(_settings()) as notifier:
                await notifier.send_message("Mensagem simples")

            assert route.called
            request = route.calls[0].request
            payload = request.read().decode()
            assert str(CHAT_ID) in payload
            assert "Mensagem simples" in payload
            assert "MarkdownV2" in payload

    @pytest.mark.asyncio
    async def test_send_digest_renders_and_sends(self) -> None:
        async with respx.mock:
            respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            ).mock(return_value=httpx.Response(200, json={"ok": True}))

            async with TelegramNotifier(_settings()) as notifier:
                await notifier.send_digest(
                    [_doc()],
                    digest_label="Diário",
                    data_geracao=FIXED_NOW,
                )

    @pytest.mark.asyncio
    async def test_long_message_split_into_chunks(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            ).mock(return_value=httpx.Response(200, json={"ok": True}))

            # Mensagem muito longa força split
            long_msg = "linha\n" * 1000
            async with TelegramNotifier(_settings()) as notifier:
                await notifier.send_message(long_msg)

            # Foi chamado múltiplas vezes (split)
            assert route.call_count > 1

    @pytest.mark.asyncio
    async def test_no_context_manager_raises(self) -> None:
        notifier = TelegramNotifier(_settings())
        with pytest.raises(RuntimeError, match="async with"):
            await notifier.send_message("x")
