"""Testes do EmailNotifier (API do Resend mockada via `respx`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

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
from monitoritcd.notifiers.email_notifier import (
    RESEND_API_URL,
    EmailNotifier,
    _format_subject,
    _saudacao_dinamica,
    _send_via_resend,
    _send_via_resend_many,
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
        RESEND_API_KEY=SecretStr("re_apikey"),
        RESEND_FROM_EMAIL="bot@example.com",
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
    async def test_send_digest_calls_resend(self) -> None:
        notifier = EmailNotifier(_settings(), env=build_jinja_env())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_resend_many",
            new=AsyncMock(return_value=(1, [])),
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Diário",
                data_geracao=FIXED_NOW,
            )
            mock_send.assert_called_once()
            kwargs = mock_send.call_args.kwargs
            assert kwargs["from_email"] == "bot@example.com"
            assert kwargs["recipients"] == ["owner@example.com"]
            assert kwargs["api_key"] == "re_apikey"
            assert "Diário" in kwargs["subject"]
            assert "<html" in kwargs["body_html"].lower()

    @pytest.mark.asyncio
    async def test_send_empty_digest(self) -> None:
        notifier = EmailNotifier(_settings())
        with patch(
            "monitoritcd.notifiers.email_notifier._send_via_resend_many",
            new=AsyncMock(return_value=(1, [])),
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
class TestSendViaResend:
    @pytest.mark.asyncio
    async def test_posts_to_resend_with_auth_and_payload(self) -> None:
        with respx.mock:
            route = respx.post(RESEND_API_URL).mock(
                return_value=httpx.Response(200, json={"id": "abc"}),
            )
            await _send_via_resend(
                api_key="re_apikey",
                from_email="bot@example.com",
                recipient="owner@example.com",
                subject="Test",
                body_html="<p>Hello</p>",
            )
            assert route.called
            request = route.calls.last.request
            assert request.headers["Authorization"] == "Bearer re_apikey"
            payload = json.loads(request.content)
            assert payload["from"] == "SefWorkStation <bot@example.com>"
            assert payload["to"] == ["owner@example.com"]
            assert payload["subject"] == "Test"
            assert payload["html"] == "<p>Hello</p>"

    @pytest.mark.asyncio
    async def test_with_plain_text_body(self) -> None:
        with respx.mock:
            route = respx.post(RESEND_API_URL).mock(
                return_value=httpx.Response(200, json={"id": "abc"}),
            )
            await _send_via_resend(
                api_key="re_apikey",
                from_email="bot@example.com",
                recipient="owner@example.com",
                subject="Test",
                body_html="<p>Hello</p>",
                body_text="Hello",
            )
            payload = json.loads(route.calls.last.request.content)
            assert payload["text"] == "Hello"

    @pytest.mark.asyncio
    async def test_with_attachments_and_reply_to(self) -> None:
        with respx.mock:
            route = respx.post(RESEND_API_URL).mock(
                return_value=httpx.Response(200, json={"id": "abc"}),
            )
            await _send_via_resend(
                api_key="re_apikey",
                from_email="bot@example.com",
                recipient="owner@example.com",
                subject="Test",
                body_html="<p>Hello</p>",
                reply_to="feedback@example.com",
                attachments=[("data.csv", "text/csv", b"a,b\n1,2\n")],
            )
            payload = json.loads(route.calls.last.request.content)
            assert payload["reply_to"] == "feedback@example.com"
            assert payload["attachments"][0]["filename"] == "data.csv"

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self) -> None:
        with respx.mock:
            respx.post(RESEND_API_URL).mock(
                return_value=httpx.Response(422, json={"message": "bad"}),
            )
            with pytest.raises(httpx.HTTPStatusError):
                await _send_via_resend(
                    api_key="re_apikey",
                    from_email="bot@example.com",
                    recipient="owner@example.com",
                    subject="Test",
                    body_html="<p>Hello</p>",
                )


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
            "monitoritcd.notifiers.email_notifier._send_via_resend_many",
            new=AsyncMock(return_value=(1, [])),
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
            "monitoritcd.notifiers.email_notifier._send_via_resend_many",
            new=AsyncMock(return_value=(1, [])),
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
            "monitoritcd.notifiers.email_notifier._send_via_resend_many",
            new=AsyncMock(return_value=(1, [])),
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
            "monitoritcd.notifiers.email_notifier._send_via_resend_many",
            new=AsyncMock(return_value=(2, [])),
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
            "monitoritcd.notifiers.email_notifier._send_via_resend_many",
            new=AsyncMock(return_value=(1, [])),
        ) as mock_send:
            await notifier.send_digest(
                [_doc()],
                digest_label="Diário",
                data_geracao=FIXED_NOW,
                recipients=["a@x.com", "a@x.com", "b@x.com"],
            )
            assert mock_send.call_args.kwargs["recipients"] == ["a@x.com", "b@x.com"]


@pytest.mark.unit
class TestSendViaResendMany:
    @pytest.mark.asyncio
    async def test_envia_individual_a_cada(self) -> None:
        with respx.mock:
            route = respx.post(RESEND_API_URL).mock(
                return_value=httpx.Response(200, json={"id": "abc"}),
            )
            enviados, falhas = await _send_via_resend_many(
                api_key="re_apikey",
                from_email="bot@example.com",
                recipients=["a@x.com", "b@x.com"],
                subject="Test",
                body_html="<p>Hi</p>",
            )
            assert enviados == 2
            assert falhas == []
            assert route.call_count == 2

    @pytest.mark.asyncio
    async def test_falha_isolada_nao_aborta(self) -> None:
        with respx.mock:
            respx.post(RESEND_API_URL).mock(
                side_effect=[
                    httpx.Response(500, json={"message": "boom"}),
                    httpx.Response(200, json={"id": "ok"}),
                ],
            )
            enviados, falhas = await _send_via_resend_many(
                api_key="re_apikey",
                from_email="bot@example.com",
                recipients=["ruim@x.com", "ok@x.com"],
                subject="Test",
                body_html="<p>Hi</p>",
            )
            assert enviados == 1
            assert falhas == ["ruim@x.com"]
