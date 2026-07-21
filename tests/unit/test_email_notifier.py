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
    _format_subject,
    _saudacao_dinamica,
    _send_via_smtp_sync,
    _send_via_smtp_sync_many,
    build_csv_attachment,
    build_jinja_env,
    build_json_attachment,
    render_email,
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
            "monitoritcd.notifiers.email_notifier._send_via_smtp_sync_many",
            return_value=(1, []),
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Diário",
                data_geracao=FIXED_NOW,
            )
            mock_send.assert_called_once()
            kwargs = mock_send.call_args.kwargs
            assert kwargs["sender"] == "bot@example.com"
            assert kwargs["recipients"] == ["owner@example.com"]
            assert kwargs["password"] == "apppass"  # noqa: S105 - test fixture
            assert "Diário" in kwargs["subject"]
            assert "<html" in kwargs["body_html"].lower()

    @pytest.mark.asyncio
    async def test_send_empty_digest(self) -> None:
        notifier = EmailNotifier(_settings())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_smtp_sync_many",
            return_value=(1, []),
        ) as mock_send:
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

    def test_smtp_with_attachments_and_reply_to(self) -> None:
        with patch("monitoritcd.notifiers.email_notifier.smtplib.SMTP") as mock_smtp:
            mock_instance = mock_smtp.return_value.__enter__.return_value
            _send_via_smtp_sync(
                sender="bot@example.com",
                password="pw",  # noqa: S106 - test fixture
                recipient="owner@example.com",
                subject="Test",
                body_html="<p>Hello</p>",
                reply_to="feedback@example.com",
                attachments=[("data.csv", "text/csv", b"a,b\n1,2\n")],
            )
            mock_instance.send_message.assert_called_once()
            sent_msg = mock_instance.send_message.call_args.args[0]
            assert sent_msg["Reply-To"] == "feedback@example.com"


@pytest.mark.unit
class TestSaudacaoDinamica:
    def test_manha_brt(self) -> None:
        # 13h UTC = 10h BRT → manhã
        assert _saudacao_dinamica(datetime(2026, 4, 24, 13, 0, tzinfo=UTC)) == "Bom dia."

    def test_tarde_brt(self) -> None:
        # 18h UTC = 15h BRT → tarde
        assert _saudacao_dinamica(datetime(2026, 4, 24, 18, 0, tzinfo=UTC)) == "Boa tarde."

    def test_noite_brt(self) -> None:
        # 23h UTC = 20h BRT → noite
        assert _saudacao_dinamica(datetime(2026, 4, 24, 23, 0, tzinfo=UTC)) == "Boa noite."

    def test_naive_treats_as_utc(self) -> None:
        # Sem tzinfo: assume UTC. 13h naive = 10h BRT → manhã.
        assert _saudacao_dinamica(datetime(2026, 4, 24, 13, 0)) == "Bom dia."  # noqa: DTZ001 — test


@pytest.mark.unit
class TestFormatSubject:
    def test_placeholders(self) -> None:
        result = _format_subject(
            "[ITCD] {label} ({date}) — {count} novidades",
            count=5,
            date_str="24/04/2026",
            label="Semanal",
        )
        assert result == "[ITCD] Semanal (24/04/2026) — 5 novidades"


@pytest.mark.unit
class TestAttachments:
    def test_csv_contains_doc(self) -> None:
        content = build_csv_attachment([_doc()])
        text = content.decode("utf-8")
        assert "doc_id" in text  # header
        assert "SP" in text

    def test_csv_empty(self) -> None:
        content = build_csv_attachment([])
        text = content.decode("utf-8")
        assert "doc_id" in text  # somente header

    def test_json_contains_doc(self) -> None:
        content = build_json_attachment([_doc()])
        import json as _json  # noqa: PLC0415

        data = _json.loads(content)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["uf"] == "SP"

    def test_json_empty(self) -> None:
        import json as _json  # noqa: PLC0415

        assert _json.loads(build_json_attachment([])) == []


@pytest.mark.unit
class TestEmailModes:
    def test_render_default_mode(self) -> None:
        subject, body = render_email(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "Diário" in subject
        assert "<html" in body.lower()

    def test_render_compacto_mode(self) -> None:
        _, body = render_email(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
            mode="compacto",
        )
        # Compacto não tem highlights/ranking
        assert "ranking" not in body.lower() or "Top" not in body

    def test_render_executivo_mode(self) -> None:
        _, body = render_email(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
            mode="executivo",
        )
        assert "Briefing" in body or "executivo" in body.lower()

    def test_render_newsletter_mode(self) -> None:
        _, body = render_email(
            [_doc()],
            digest_label="Edição Especial",
            data_geracao=FIXED_NOW,
            mode="newsletter",
        )
        assert "MonitorITCD" in body

    def test_render_with_subject_template(self) -> None:
        subject, _ = render_email(
            [_doc()],
            digest_label="Semanal",
            data_geracao=FIXED_NOW,
            subject_template="ITCD: {count} de {date}",
        )
        assert subject == "ITCD: 1 de 24/04/2026"

    def test_render_with_explicit_subject(self) -> None:
        subject, _ = render_email(
            [_doc()],
            digest_label="X",
            data_geracao=FIXED_NOW,
            subject="Override",
        )
        assert subject == "Override"

    def test_render_with_footer_links(self) -> None:
        _, body = render_email(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
            bot_url="https://t.me/test_bot",
            dashboard_url="https://example.com/dash",
            repo_url="https://github.com/x/y",
        )
        assert "Ver no bot" in body
        assert "Dashboard" in body


@pytest.mark.unit
class TestSendDigestExtras:
    @pytest.mark.asyncio
    async def test_send_with_csv_and_json(self) -> None:
        notifier = EmailNotifier(_settings(), env=build_jinja_env())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_smtp_sync_many",
            return_value=(1, []),
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Semanal",
                data_geracao=FIXED_NOW,
                attach_csv=True,
                attach_json=True,
                bot_url="https://t.me/x",
            )
            kwargs = mock_send.call_args.kwargs
            assert kwargs["attachments"] is not None
            assert len(kwargs["attachments"]) == 2

    @pytest.mark.asyncio
    async def test_send_with_reply_to(self) -> None:
        notifier = EmailNotifier(_settings(), env=build_jinja_env())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_smtp_sync_many",
            return_value=(1, []),
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Diário",
                data_geracao=FIXED_NOW,
                reply_to="feedback@example.com",
            )
            kwargs = mock_send.call_args.kwargs
            assert kwargs["reply_to"] == "feedback@example.com"

    @pytest.mark.asyncio
    async def test_send_executivo_mode(self) -> None:
        notifier = EmailNotifier(_settings(), env=build_jinja_env())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_smtp_sync_many",
            return_value=(1, []),
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Mensal",
                data_geracao=FIXED_NOW,
                mode="executivo",
            )
            kwargs = mock_send.call_args.kwargs
            assert "<html" in kwargs["body_html"].lower()


@pytest.mark.unit
class TestSendDigestRecipients:
    """Fase 2 — envio a múltiplos destinatários (owner + inscritos opt-in)."""

    @pytest.mark.asyncio
    async def test_recipients_repassados(self) -> None:
        notifier = EmailNotifier(_settings(), env=build_jinja_env())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_smtp_sync_many",
            return_value=(2, []),
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Diário",
                data_geracao=FIXED_NOW,
                recipients=["owner@example.com", "servidor@sef.mg.gov.br"],
            )
            assert mock_send.call_args.kwargs["recipients"] == [
                "owner@example.com",
                "servidor@sef.mg.gov.br",
            ]

    @pytest.mark.asyncio
    async def test_recipients_dedup(self) -> None:
        notifier = EmailNotifier(_settings(), env=build_jinja_env())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_smtp_sync_many",
            return_value=(1, []),
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Diário",
                data_geracao=FIXED_NOW,
                recipients=["a@x.com", "a@x.com", "b@x.com"],
            )
            assert mock_send.call_args.kwargs["recipients"] == ["a@x.com", "b@x.com"]


@pytest.mark.unit
class TestSendViaSMTPMany:
    def test_envia_individual_a_cada(self) -> None:
        with patch("monitoritcd.notifiers.email_notifier.smtplib.SMTP") as mock_smtp:
            inst = mock_smtp.return_value.__enter__.return_value
            enviados, falhas = _send_via_smtp_sync_many(
                sender="bot@example.com",
                password="pw",  # noqa: S106 - test fixture
                recipients=["a@x.com", "b@x.com"],
                subject="Test",
                body_html="<p>Hi</p>",
            )
            assert enviados == 2
            assert falhas == []
            inst.login.assert_called_once()  # 1 conexão para todos
            assert inst.send_message.call_count == 2

    def test_falha_isolada_nao_aborta(self) -> None:
        with patch("monitoritcd.notifiers.email_notifier.smtplib.SMTP") as mock_smtp:
            inst = mock_smtp.return_value.__enter__.return_value
            inst.send_message.side_effect = [OSError("boom"), None]
            enviados, falhas = _send_via_smtp_sync_many(
                sender="bot@example.com",
                password="pw",  # noqa: S106 - test fixture
                recipients=["ruim@x.com", "ok@x.com"],
                subject="Test",
                body_html="<p>Hi</p>",
            )
            assert enviados == 1
            assert falhas == ["ruim@x.com"]
