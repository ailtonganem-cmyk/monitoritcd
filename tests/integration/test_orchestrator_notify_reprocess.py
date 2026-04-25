"""Testes para notify_documents() e reprocess_documents() no orchestrator.

Cobre os caminhos novos: push CRITICO, digest ALTA/NORMAL/BAIXA, reclassificação
em batch. Mocka HTTP do Telegram via respx e patch SMTP do EmailNotifier.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

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
from monitoritcd.llm.fake import FakeLLMProvider
from monitoritcd.orchestrator import (
    RunReport,
    notify_documents,
    reprocess_documents,
)
from monitoritcd.storage import InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import Iterable

FIXED_NOW = datetime(2026, 4, 25, tzinfo=UTC)
OWNER = "owner-test"
TOKEN = "1234567890:fakeFAKE_token_abc"  # noqa: S105 - test fixture
CHAT_ID = 123456


def _settings() -> Settings:
    return Settings(
        OWNER_ID=OWNER,
        OWNER_EMAIL="o@example.com",
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


def _make_doc(doc_id: str, *, tier: SeverityTier) -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw=f"Item {doc_id}",
        url=f"https://x.gov.br/{doc_id}",
        fetched_at=FIXED_NOW,
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
    llm = LLMResult(
        classified_at=FIXED_NOW,
        llm_model="fake-llm",
        llm_prompt_version="v1",
        tipo=TipoAto.PROJETO_LEI,
        relevancia=8,
        severity_tier=tier,
        resumo="Resumo.",
    )
    return Documento(
        owner_id=OWNER,
        doc_id=doc_id,
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )


async def _save_all(storage: InMemoryStorage, docs: Iterable[Documento]) -> None:
    for d in docs:
        await storage.save_documento(d)


@pytest.mark.integration
class TestNotifyDocuments:
    @pytest.mark.asyncio
    async def test_empty_list_returns_early(self) -> None:
        storage = InMemoryStorage(OWNER)
        report = RunReport(run_id="t", started_at=FIXED_NOW)
        await notify_documents([], settings=_settings(), storage=storage, report=report)
        assert report.items_notified_telegram == 0
        assert report.items_notified_email == 0

    @pytest.mark.asyncio
    async def test_critico_pushes_immediate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = InMemoryStorage(OWNER)
        doc = _make_doc("d1", tier=SeverityTier.CRITICO)
        await _save_all(storage, [doc])
        report = RunReport(run_id="t", started_at=FIXED_NOW)

        # Patch EmailNotifier.send_digest para no-op (não há digest_docs aqui)
        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            await notify_documents(
                [doc],
                settings=_settings(),
                storage=storage,
                report=report,
            )

        assert report.items_notified_telegram == 1
        # Status deve ter mudado para NOTIFIED
        loaded = await storage.get_documento(doc.doc_id)
        assert loaded is not None
        assert loaded.status == StatusDocumento.NOTIFIED

    @pytest.mark.asyncio
    async def test_digest_path_alta_normal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = InMemoryStorage(OWNER)
        d_alta = _make_doc("d1", tier=SeverityTier.ALTA)
        d_normal = _make_doc("d2", tier=SeverityTier.NORMAL)
        await _save_all(storage, [d_alta, d_normal])
        report = RunReport(run_id="t", started_at=FIXED_NOW)

        # Patch EmailNotifier.send_digest para no-op (evita SMTP real)
        from monitoritcd.notifiers import email_notifier as _email_mod  # noqa: PLC0415

        async def _fake_send_digest(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        monkeypatch.setattr(_email_mod.EmailNotifier, "send_digest", _fake_send_digest)

        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            await notify_documents(
                [d_alta, d_normal],
                settings=_settings(),
                storage=storage,
                report=report,
                digest_label="Diário",
            )

        assert report.items_notified_telegram == 2
        assert report.items_notified_email == 2
        # Ambos devem ter ficado NOTIFIED
        for did in ("d1", "d2"):
            loaded = await storage.get_documento(did)
            assert loaded is not None
            assert loaded.status == StatusDocumento.NOTIFIED


@pytest.mark.integration
class TestReprocessDocuments:
    @pytest.mark.asyncio
    async def test_empty_storage_returns_early(self) -> None:
        storage = InMemoryStorage(OWNER)
        report = await reprocess_documents(
            storage=storage,
            llm_provider=FakeLLMProvider(),
            limit=10,
        )
        assert report.items_classified == 0
        assert report.finished_at is not None

    @pytest.mark.asyncio
    async def test_reprocesses_existing_docs(self) -> None:
        storage = InMemoryStorage(OWNER)
        d1 = _make_doc("d1", tier=SeverityTier.NORMAL)
        d2 = _make_doc("d2", tier=SeverityTier.NORMAL)
        await _save_all(storage, [d1, d2])

        report = await reprocess_documents(
            storage=storage,
            llm_provider=FakeLLMProvider(),
            limit=10,
        )
        assert report.items_classified == 2
        assert report.finished_at is not None

    @pytest.mark.asyncio
    async def test_filtra_por_uf(self) -> None:
        storage = InMemoryStorage(OWNER)
        d_sp = _make_doc("d1", tier=SeverityTier.NORMAL)
        await _save_all(storage, [d_sp])

        report = await reprocess_documents(
            storage=storage,
            llm_provider=FakeLLMProvider(),
            uf="SP",
            limit=10,
        )
        # SP existe → reclassifica
        assert report.items_classified == 1
