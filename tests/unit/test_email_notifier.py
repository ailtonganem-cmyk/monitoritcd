"""Testes do EmailNotifier (SMTP mockado)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
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
from monitoritcd.notifiers.email_notifier import (
    EmailNotifier,
    _send_via_smtp_sync,
    build_jinja_env,
)

FIXED_NOW = datetime(2026, 4, 24, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(
        OWNER_ID="o",
        OWNER_EMAIL="owner@example.com",
        GEMINI_API_KEY=SecretStr("g"),
        GMAIL_USER="bot@example.com",
        GMAIL_APP_PASSWORD=SecretStr("apppass"),
        TELEGRAM_BOT_TOKEN=SecretStr("t"),
        TELEGRAM_OWNER_CHAT_ID=1,
        TELEGRAM_WEBHOOK_SECRET=SecretStr("ws"),
        FIREBASE_PROJECT_ID="p",
        FIREBASE_STORAGE_BUCKET="p.appspot.com",
        FIREBASE_SERVICE_ACCOUNT_JSON=SecretStr("{}"),
    )


def _doc() -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw="x",
        url="https://x.gov.br/",
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
        tipo=TipoAto.NOTICIA,
        relevancia=7,
        severity_tier=SeverityTier.NORMAL,
        resumo="x",
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
class TestEmailNotifier:
    @pytest.mark.asyncio
    async def test_send_digest_calls_smtp(self) -> None:
        notifier = EmailNotifier(_settings(), env=build_jinja_env())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_smtp_sync",
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Diário",
                data_geracao=FIXED_NOW,
            )
            mock_send.assert_called_once()
            kwargs = mock_send.call_args.kwargs
            assert kwargs["sender"] == "bot@example.com"
            assert kwargs["recipient"] == "owner@example.com"
            assert kwargs["password"] == "apppass"  # noqa: S105 - test fixture
            assert "Diário" in kwargs["subject"]
            assert "<html" in kwargs["body_html"].lower()

    @pytest.mark.asyncio
    async def test_send_empty_digest(self) -> None:
        notifier = EmailNotifier(_settings())
        with patch("monitoritcd.notifiers.email_notifier._send_via_smtp_sync") as mock_send:
            await notifier.send_digest(
                [],
                digest_label="Semanal",
                data_geracao=FIXED_NOW,
            )
            mock_send.assert_called_once()
            kwargs = mock_send.call_args.kwargs
            assert "0 novidades" in kwargs["subject"]


@pytest.mark.unit
class TestSendViaSMTP:
    def test_smtp_login_and_send(self) -> None:
        # Mocka smtplib.SMTP completamente
        with patch("monitoritcd.notifiers.email_notifier.smtplib.SMTP") as mock_smtp:
            mock_instance = mock_smtp.return_value.__enter__.return_value
            _send_via_smtp_sync(
                sender="bot@example.com",
                password="pw",  # noqa: S106 - test fixture
                recipient="owner@example.com",
                subject="Test",
                body_html="<p>Hello</p>",
            )
            mock_smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
            mock_instance.starttls.assert_called_once()
            mock_instance.login.assert_called_once_with("bot@example.com", "pw")
            mock_instance.send_message.assert_called_once()
