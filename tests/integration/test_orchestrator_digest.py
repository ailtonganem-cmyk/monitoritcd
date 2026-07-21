"""Testes para run_digest() no orchestrator — IDEAS.md #101/#102.

Mocka HTTP do Telegram via respx e patch do EmailNotifier.send_digest,
mesmo padrão de test_orchestrator_notify_reprocess.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from monitoritcd.orchestrator import run_digest
from monitoritcd.storage import InMemoryStorage

FIXED_NOW = datetime(2026, 4, 25, tzinfo=UTC)
OWNER = "owner-test"
TOKEN = "1234567890:fakeFAKE_token_abc"  # noqa: S105 - test fixture


def _settings() -> Settings:
    return Settings(
        OWNER_ID=OWNER,
        OWNER_EMAIL="o@example.com",
        GEMINI_API_KEY=SecretStr("g"),
        GMAIL_USER="bot@example.com",
        GMAIL_APP_PASSWORD=SecretStr("p"),
        TELEGRAM_BOT_TOKEN=SecretStr(TOKEN),
        TELEGRAM_OWNER_CHAT_ID=123456,
        TELEGRAM_WEBHOOK_SECRET=SecretStr("ws"),
        FIREBASE_PROJECT_ID="p",
        FIREBASE_STORAGE_BUCKET="p.appspot.com",
        FIREBASE_SERVICE_ACCOUNT_JSON=SecretStr("{}"),
    )


def _make_doc(doc_id: str, *, fetched_at: datetime, classified: bool = True) -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw=f"Item {doc_id}",
        url=f"https://x.gov.br/{doc_id}",
        fetched_at=fetched_at,
        content_hash=("a" * 63) + doc_id[-1],
    )
    src = Source(
        id="src",
        uf="SP",
        nome="x",
        tipo=TipoFonte.SEFAZ,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = (
        LLMResult(
            classified_at=fetched_at,
            llm_model="fake-llm",
            llm_prompt_version="v1",
            tipo=TipoAto.PROJETO_LEI,
            relevancia=8,
            severity_tier=SeverityTier.NORMAL,
            resumo="Resumo.",
        )
        if classified
        else None
    )
    return Documento(
        owner_id=OWNER,
        doc_id=doc_id,
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED if classified else StatusDocumento.PENDING,
    )


@pytest.mark.integration
class TestRunDigest:
    @pytest.mark.asyncio
    async def test_periodicidade_invalida_levanta_erro(self) -> None:
        storage = InMemoryStorage(OWNER)
        with pytest.raises(ValueError, match="periodicidade inválida"):
            await run_digest(_settings(), storage=storage, periodicidade="diario")

    @pytest.mark.asyncio
    async def test_sem_documentos_retorna_cedo(self) -> None:
        storage = InMemoryStorage(OWNER)
        report = await run_digest(_settings(), storage=storage, periodicidade="semanal")
        assert report.items_notified_telegram == 0
        assert report.items_notified_email == 0
        assert report.finished_at is not None

    @pytest.mark.asyncio
    async def test_ignora_documentos_fora_da_janela(self) -> None:
        storage = InMemoryStorage(OWNER)
        antigo = _make_doc("d1", fetched_at=FIXED_NOW - timedelta(days=40))
        await storage.save_documento(antigo)

        report = await run_digest(_settings(), storage=storage, periodicidade="semanal")
        assert report.items_notified_telegram == 0
        assert report.items_classified == 0

    @pytest.mark.asyncio
    async def test_ignora_nao_classificados(self) -> None:
        storage = InMemoryStorage(OWNER)
        pendente = _make_doc("d1", fetched_at=datetime.now(UTC), classified=False)
        await storage.save_documento(pendente)

        report = await run_digest(_settings(), storage=storage, periodicidade="semanal")
        assert report.items_collected == 1
        assert report.items_classified == 0
        assert report.items_notified_telegram == 0

    @pytest.mark.asyncio
    async def test_envia_semanal_telegram_e_email(self, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = InMemoryStorage(OWNER)
        doc = _make_doc("d1", fetched_at=datetime.now(UTC))
        await storage.save_documento(doc)

        from monitoritcd.notifiers import email_notifier as _email_mod  # noqa: PLC0415

        capturado: dict[str, object] = {}

        async def _fake_send_digest(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            capturado["recipients"] = kwargs.get("recipients")
            capturado["digest_label"] = kwargs.get("digest_label")

        monkeypatch.setattr(_email_mod.EmailNotifier, "send_digest", _fake_send_digest)

        async with respx.mock:
            route = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            report = await run_digest(_settings(), storage=storage, periodicidade="semanal")

        assert route.called
        assert report.items_notified_telegram == 1
        assert report.items_notified_email == 1
        assert capturado["recipients"] == ["o@example.com"]
        assert capturado["digest_label"] == "Semanal"
        assert report.errors == []

    @pytest.mark.asyncio
    async def test_mensal_inclui_inscritos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = InMemoryStorage(OWNER)
        storage._email_subscribers = ["sub@sef.mg.gov.br"]
        doc = _make_doc("d1", fetched_at=datetime.now(UTC))
        await storage.save_documento(doc)

        from monitoritcd.notifiers import email_notifier as _email_mod  # noqa: PLC0415

        capturado: dict[str, object] = {}

        async def _fake_send_digest(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            capturado["recipients"] = kwargs.get("recipients")
            capturado["digest_label"] = kwargs.get("digest_label")

        monkeypatch.setattr(_email_mod.EmailNotifier, "send_digest", _fake_send_digest)

        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            report = await run_digest(_settings(), storage=storage, periodicidade="mensal")

        assert capturado["recipients"] == ["o@example.com", "sub@sef.mg.gov.br"]
        assert capturado["digest_label"] == "Mensal"
        assert report.items_notified_email == 1

    @pytest.mark.asyncio
    async def test_falha_telegram_nao_impede_email(self, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = InMemoryStorage(OWNER)
        doc = _make_doc("d1", fetched_at=datetime.now(UTC))
        await storage.save_documento(doc)

        from monitoritcd.notifiers import email_notifier as _email_mod  # noqa: PLC0415

        async def _fake_send_digest(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        monkeypatch.setattr(_email_mod.EmailNotifier, "send_digest", _fake_send_digest)

        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(500),
            )
            report = await run_digest(_settings(), storage=storage, periodicidade="semanal")

        assert report.items_notified_telegram == 0
        assert report.items_notified_email == 1
        assert len(report.errors) == 1
        assert "digest_telegram" in report.errors[0]

    @pytest.mark.asyncio
    async def test_falha_email_nao_impede_telegram(self, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = InMemoryStorage(OWNER)
        doc = _make_doc("d1", fetched_at=datetime.now(UTC))
        await storage.save_documento(doc)

        from monitoritcd.notifiers import email_notifier as _email_mod  # noqa: PLC0415

        async def _fake_send_digest(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            msg = "falha simulada no envio"
            raise RuntimeError(msg)

        monkeypatch.setattr(_email_mod.EmailNotifier, "send_digest", _fake_send_digest)

        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            report = await run_digest(_settings(), storage=storage, periodicidade="semanal")

        assert report.items_notified_telegram == 1
        assert report.items_notified_email == 0
        assert len(report.errors) == 1
        assert "digest_email" in report.errors[0]

    @pytest.mark.asyncio
    async def test_falha_ao_ler_inscritos_nao_impede_envio_ao_owner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = InMemoryStorage(OWNER)
        doc = _make_doc("d1", fetched_at=datetime.now(UTC))
        await storage.save_documento(doc)

        async def _boom() -> list[str]:
            msg = "leitura de inscritos falhou"
            raise RuntimeError(msg)

        monkeypatch.setattr(storage, "list_email_subscribers", _boom)

        from monitoritcd.notifiers import email_notifier as _email_mod  # noqa: PLC0415

        capturado: dict[str, object] = {}

        async def _fake_send_digest(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            capturado["recipients"] = kwargs.get("recipients")

        monkeypatch.setattr(_email_mod.EmailNotifier, "send_digest", _fake_send_digest)

        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            report = await run_digest(_settings(), storage=storage, periodicidade="semanal")

        assert capturado["recipients"] == ["o@example.com"]
        assert report.items_notified_email == 1
