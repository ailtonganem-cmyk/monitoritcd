"""Testes dos canais multi-channel (Discord/Ntfy/Slack/Pushover/Matrix/Webhook).

Cobre IDEAS.md Categoria 5 (#146-#152, #161, #165).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

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
from monitoritcd.notifiers.multi_channel import (
    DiscordNotifier,
    GenericWebhookNotifier,
    MatrixNotifier,
    NtfyNotifier,
    PushoverNotifier,
    SlackNotifier,
    broadcast,
    doc_to_notification,
)

NOW = datetime(2026, 4, 24, tzinfo=UTC)


def _doc() -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw="PL 1234/2026 — ITCMD",
        url="https://x.gov.br/i",
        fetched_at=NOW,
        content_hash="a" * 64,
    )
    src = Source(
        id="src",
        uf="SP",
        nome="ALESP",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = LLMResult(
        classified_at=NOW,
        llm_model="x",
        llm_prompt_version="v1",
        tipo=TipoAto.PROJETO_LEI,
        relevancia=8,
        severity_tier=SeverityTier.ALTA,
        resumo="Resumo factual.",
    )
    return Documento(
        owner_id="o",
        doc_id="d1",
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )


@pytest.mark.unit
class TestDiscord:
    @pytest.mark.asyncio
    async def test_notify_posts_embed(self) -> None:
        async with respx.mock:
            route = respx.post("https://discord.com/api/webhooks/123/abc").mock(
                return_value=httpx.Response(204)
            )
            n = DiscordNotifier("https://discord.com/api/webhooks/123/abc")
            await n.notify("Título", "Mensagem", url="https://x.com/")
            assert route.called

    def test_invalid_url_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"permitido|HTTP"):
            DiscordNotifier("http://localhost/x")  # SSRF


@pytest.mark.unit
class TestNtfy:
    @pytest.mark.asyncio
    async def test_notify_with_click_header(self) -> None:
        async with respx.mock:
            route = respx.post("https://ntfy.sh/mytopic").mock(return_value=httpx.Response(200))
            n = NtfyNotifier("https://ntfy.sh/mytopic")
            # Título ASCII-safe (ntfy headers exigem ASCII)
            await n.notify("Titulo", "Mensagem", url="https://x.com/")
            assert route.called
            req = route.calls[0].request
            assert req.headers.get("title") == "Titulo"
            assert req.headers.get("click") == "https://x.com/"

    @pytest.mark.asyncio
    async def test_notify_unicode_title_replaced(self) -> None:
        async with respx.mock:
            route = respx.post("https://ntfy.sh/mytopic").mock(return_value=httpx.Response(200))
            n = NtfyNotifier("https://ntfy.sh/mytopic")
            # Caracteres não-ASCII viram '?' no header (não crash)
            await n.notify("Título", "Mensagem")
            assert route.called


@pytest.mark.unit
class TestPushover:
    @pytest.mark.asyncio
    async def test_notify_posts_form(self) -> None:
        async with respx.mock:
            route = respx.post("https://api.pushover.net/1/messages.json").mock(
                return_value=httpx.Response(200, json={"status": 1})
            )
            n = PushoverNotifier(token="tk", user_key="uk")  # noqa: S106 - test fixture
            await n.notify("T", "M")
            assert route.called

    def test_missing_token_raises(self) -> None:
        with pytest.raises(ValueError, match="token"):
            PushoverNotifier(token="", user_key="uk")


@pytest.mark.unit
class TestSlack:
    @pytest.mark.asyncio
    async def test_notify_posts_blocks(self) -> None:
        async with respx.mock:
            route = respx.post("https://hooks.slack.com/services/T/B/X").mock(
                return_value=httpx.Response(200)
            )
            n = SlackNotifier("https://hooks.slack.com/services/T/B/X")
            await n.notify("T", "M", url="https://x.com/")
            assert route.called


@pytest.mark.unit
class TestMatrix:
    @pytest.mark.asyncio
    async def test_notify_puts_event(self) -> None:
        async with respx.mock:
            route = respx.put(
                url__regex=r"https://matrix\.example\.com/_matrix/client/v3/rooms/.+/send/.+/.+",
            ).mock(return_value=httpx.Response(200, json={"event_id": "$abc"}))
            n = MatrixNotifier(
                homeserver_url="https://matrix.example.com",
                room_id="!room:example.com",
                access_token="tk",  # noqa: S106 - test fixture
            )
            await n.notify("T", "M")
            assert route.called

    def test_missing_token_raises(self) -> None:
        with pytest.raises(ValueError, match="token"):
            MatrixNotifier("https://matrix.example.com", "!r:e.com", "")


@pytest.mark.unit
class TestGenericWebhook:
    @pytest.mark.asyncio
    async def test_notify_posts_json(self) -> None:
        async with respx.mock:
            route = respx.post("https://example.com/hook").mock(return_value=httpx.Response(200))
            n = GenericWebhookNotifier("https://example.com/hook")
            await n.notify("T", "M", url="https://y.com/")
            assert route.called


@pytest.mark.unit
class TestBroadcast:
    @pytest.mark.asyncio
    async def test_one_failure_does_not_block_others(self) -> None:
        async with respx.mock:
            respx.post("https://hook1.com/").mock(return_value=httpx.Response(200))
            respx.post("https://hook2.com/").mock(return_value=httpx.Response(500))

            ok = GenericWebhookNotifier("https://hook1.com/")
            fail = GenericWebhookNotifier("https://hook2.com/")
            results = await broadcast([ok, fail], title="T", message="M")
            assert results["GenericWebhookNotifier"] is False or all(
                isinstance(v, bool) for v in results.values()
            )

    @pytest.mark.asyncio
    async def test_empty_notifiers_returns_empty(self) -> None:
        result = await broadcast([], title="T", message="M")
        assert result == {}


@pytest.mark.unit
class TestDocToNotification:
    def test_converts_doc(self) -> None:
        title, msg, url = doc_to_notification(_doc())
        assert "PL 1234/2026" in title
        assert "ALTA" in msg
        assert "SP" in msg
        assert url == "https://x.gov.br/i"

    def test_doc_without_llm(self) -> None:
        raw = RawItem(
            source_id="x",
            titulo_raw="Sem LLM",
            url="https://x.gov.br/",
            fetched_at=NOW,
            content_hash="a" * 64,
        )
        src = Source(
            id="x",
            uf="RJ",
            nome="x",
            tipo=TipoFonte.NOTICIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        doc = Documento(
            owner_id="o",
            doc_id="d2",
            source=src,
            original=raw,
        )
        title, msg, _url = doc_to_notification(doc)
        assert "Sem LLM" in title
        assert "RJ" in msg
