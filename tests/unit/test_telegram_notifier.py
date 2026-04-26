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
from monitoritcd.notifiers.telegram_actions import build_item_keyboard
from monitoritcd.notifiers.telegram_notifier import (
    TelegramNotifier,
    is_dnd_window,
    render_quote,
    render_telegram,
)

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

    @pytest.mark.asyncio
    async def test_send_message_with_keyboard(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            ).mock(
                return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})
            )

            kb = build_item_keyboard("doc_1", url="https://x.gov.br/")
            async with TelegramNotifier(_settings()) as notifier:
                msg_id = await notifier.send_message("Texto", keyboard=kb)

            assert msg_id == 42
            payload = route.calls[0].request.read().decode()
            assert "inline_keyboard" in payload
            assert "callback_data" in payload

    @pytest.mark.asyncio
    async def test_send_message_with_reply_to(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            ).mock(return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}))

            async with TelegramNotifier(_settings()) as notifier:
                await notifier.send_message("Texto", reply_to_message_id=99)

            payload = route.calls[0].request.read().decode()
            assert "reply_parameters" in payload
            assert "99" in payload

    @pytest.mark.asyncio
    async def test_pin_message(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/pinChatMessage",
            ).mock(return_value=httpx.Response(200, json={"ok": True}))

            async with TelegramNotifier(_settings()) as notifier:
                await notifier.pin_message(42)

            assert route.called
            payload = route.calls[0].request.read().decode()
            assert "42" in payload

    @pytest.mark.asyncio
    async def test_unpin_message(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/unpinChatMessage",
            ).mock(return_value=httpx.Response(200, json={"ok": True}))

            async with TelegramNotifier(_settings()) as notifier:
                await notifier.unpin_message(42)

            assert route.called

    @pytest.mark.asyncio
    async def test_edit_message_text(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/editMessageText",
            ).mock(return_value=httpx.Response(200, json={"ok": True}))

            async with TelegramNotifier(_settings()) as notifier:
                await notifier.edit_message_text(42, "Atualizado")

            payload = route.calls[0].request.read().decode()
            assert "Atualizado" in payload
            assert "42" in payload

    @pytest.mark.asyncio
    async def test_send_chat_action(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendChatAction",
            ).mock(return_value=httpx.Response(200, json={"ok": True}))

            async with TelegramNotifier(_settings()) as notifier:
                await notifier.send_chat_action("typing")

            assert route.called

    @pytest.mark.asyncio
    async def test_send_chat_action_failure_does_not_raise(self) -> None:
        # send_chat_action é fire-and-forget; falha de rede não derruba pipeline
        async with respx.mock:
            respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendChatAction",
            ).mock(side_effect=httpx.ConnectError("network down"))

            async with TelegramNotifier(_settings()) as notifier:
                # Não deve lançar
                await notifier.send_chat_action("typing")

    @pytest.mark.asyncio
    async def test_send_digest_with_dnd_window_skipped(self) -> None:
        # 03h UTC = 00h BRT (dentro de DND 22h-7h)
        dnd_time = datetime(2026, 4, 24, 3, tzinfo=UTC)
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            ).mock(return_value=httpx.Response(200, json={"ok": True}))

            async with TelegramNotifier(_settings()) as notifier:
                msg_id = await notifier.send_digest(
                    [_doc()],
                    digest_label="x",
                    data_geracao=dnd_time,
                    respect_dnd=True,
                )

            assert msg_id is None
            assert not route.called

    @pytest.mark.asyncio
    async def test_send_digest_with_keyboard_single_doc(self) -> None:
        async with respx.mock:
            route = respx.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            ).mock(return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 7}}))

            async with TelegramNotifier(_settings()) as notifier:
                await notifier.send_digest(
                    [_doc()],
                    digest_label="x",
                    data_geracao=FIXED_NOW,
                    with_keyboards=True,
                )

            payload = route.calls[0].request.read().decode()
            assert "inline_keyboard" in payload


@pytest.mark.unit
class TestRenderGrouped:
    def test_group_by_uf(self) -> None:
        text = render_telegram(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
            group_by="uf",
        )
        assert "SP" in text

    def test_group_by_tipo(self) -> None:
        text = render_telegram(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
            group_by="tipo",
        )
        # TipoAto.PROJETO_LEI maps to "Projeto de Lei" via TIPO_LABELS
        # (escape adiciona \\) na renderização)
        assert "Projeto de Lei" in text

    def test_no_group_by_uses_default_template(self) -> None:
        text = render_telegram(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
            group_by=None,
        )
        # Default template tem "MonitorITCD"
        assert "MonitorITCD" in text


@pytest.mark.unit
class TestDND:
    def test_dnd_window_inicio(self) -> None:
        # 22h BRT = 01h UTC do dia seguinte
        assert is_dnd_window(datetime(2026, 4, 24, 1, tzinfo=UTC)) is True

    def test_dnd_window_meio(self) -> None:
        # 03h BRT = 06h UTC
        assert is_dnd_window(datetime(2026, 4, 24, 6, tzinfo=UTC)) is True

    def test_fora_dnd_meio_dia(self) -> None:
        # 12h BRT = 15h UTC
        assert is_dnd_window(datetime(2026, 4, 24, 15, tzinfo=UTC)) is False

    def test_naive_datetime_treated_as_utc(self) -> None:
        # 03h naive = 03h UTC = 00h BRT (dentro DND)
        assert is_dnd_window(datetime(2026, 4, 24, 3)) is True  # noqa: DTZ001 — test

    def test_janela_nao_cruzando_meia_noite(self) -> None:
        # Janela 9h-17h não cruza meia-noite; testa branch alternativo
        # 12h BRT = 15h UTC
        assert is_dnd_window(datetime(2026, 4, 24, 15, tzinfo=UTC), inicio=9, fim=17) is True


@pytest.mark.unit
class TestRenderQuote:
    def test_quote_simples(self) -> None:
        result = render_quote("linha 1\nlinha 2")
        assert ">linha 1" in result
        assert ">linha 2" in result

    def test_quote_escapa_markdown(self) -> None:
        result = render_quote("linha com * e _ caracteres")
        # `*` e `_` precisam estar escapados para MarkdownV2
        assert r"\*" in result
        assert r"\_" in result

    def test_quote_uma_linha(self) -> None:
        result = render_quote("apenas uma")
        assert result.startswith(">")
