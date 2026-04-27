"""Testes para os caminhos de erro do orchestrator.

Cobre exception handlers que normalmente nao executam: classify falhando,
save_documento falhando, healthcheck com erro de rede, audit append falhando,
reprocess com erros, push CRITICO falhando, status update apos digest falhando.

Princípio: error handling do orchestrator e' defense in depth — uma fonte
falhar nao pode derrubar o pipeline. Esses testes provam isso.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from pydantic import HttpUrl, SecretStr

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
from monitoritcd.llm.fallback import LLMProvidersExhaustedError
from monitoritcd.orchestrator import (
    RunReport,
    classify_and_store,
    notify_documents,
    ping_healthcheck,
    reprocess_documents,
)
from monitoritcd.storage import InMemoryStorage

if TYPE_CHECKING:
    from collections.abc import Iterable

NOW = datetime(2026, 4, 25, tzinfo=UTC)
OWNER = "owner-test"
TOKEN = "1234567890:fakeFAKE_token_abc"  # noqa: S105 - test fixture
CHAT_ID = 123456


def _settings(*, healthcheck_url: str | None = None) -> Settings:
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
        HEALTHCHECKS_URL=HttpUrl(healthcheck_url) if healthcheck_url else None,
    )


def _make_doc(doc_id: str, *, tier: SeverityTier = SeverityTier.NORMAL) -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw=f"Item {doc_id}",
        url=f"https://x.gov.br/{doc_id}",
        fetched_at=NOW,
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
        classified_at=NOW,
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


def _raw(doc_id: str) -> tuple[Source, RawItem]:
    src = Source(
        id="src",
        uf="SP",
        nome="x",
        tipo=TipoFonte.SEFAZ,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    # Hash precisa ser único nos primeiros 16 chars (doc_id usa content_hash[:16])
    last_char = doc_id[-1]
    raw = RawItem(
        source_id="src",
        titulo_raw=f"PL ITCMD {doc_id}",
        url=f"https://x.gov.br/{doc_id}",
        fetched_at=NOW,
        content_hash=(last_char * 16) + ("0" * 48),
    )
    return src, raw


@pytest.mark.integration
class TestRunReportDuration:
    def test_duration_zero_quando_finished_at_none(self) -> None:
        report = RunReport(run_id="t", started_at=NOW)
        # finished_at default = None -> duration_seconds = 0.0 (linha 121)
        assert report.duration_seconds == 0.0


@pytest.mark.integration
class TestClassifyAndStoreEdgeCases:
    @pytest.mark.asyncio
    async def test_lista_vazia_retorna_vazia(self) -> None:
        # Linha 202: early return em items=[]
        storage = InMemoryStorage(OWNER)
        report = RunReport(run_id="t", started_at=NOW)
        result = await classify_and_store(
            [],
            llm_provider=FakeLLMProvider(),
            storage=storage,
            owner_id=OWNER,
            report=report,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_descartado_nao_persistido(self) -> None:
        # Linha 225: LLM marca como DESCARTADO -> nao salva
        class _DescartadoLLM:
            name = "descartado-llm"

            async def classify_batch(
                self, items_text: list[str], *, system_prompt: str | None = None
            ) -> list[dict[str, Any]]:
                # Relevancia 1 mapeia para DESCARTADO em map_relevancia_to_tier
                return [
                    {
                        "tipo": "noticia",
                        "topics": ["itcd"],
                        "relevancia": 1,
                        "resumo": t[:50],
                        "numero_ato": None,
                        "orgao_emissor": None,
                        "tags": [],
                    }
                    for t in items_text
                ]

        storage = InMemoryStorage(OWNER)
        report = RunReport(run_id="t", started_at=NOW)
        items = [_raw("d1")]
        result = await classify_and_store(
            items,
            llm_provider=_DescartadoLLM(),
            storage=storage,
            owner_id=OWNER,
            report=report,
        )
        assert result == []  # nada salvo
        assert report.items_stored == 0


@pytest.mark.integration
class TestClassifyAndStoreErrorPaths:
    @pytest.mark.asyncio
    async def test_classify_batch_falha_continua(self) -> None:
        # LLM levanta ValueError -> orchestrator captura, registra, segue.
        class _FailingLLM:
            name = "failing"

            async def classify_batch(
                self, items_text: list[str], *, system_prompt: str | None = None
            ) -> list[dict[str, Any]]:
                msg = "LLM offline"
                raise ValueError(msg)

        storage = InMemoryStorage(OWNER)
        report = RunReport(run_id="t", started_at=NOW)
        items = [_raw("d1")]
        result = await classify_and_store(
            items,
            llm_provider=_FailingLLM(),
            storage=storage,
            owner_id=OWNER,
            report=report,
        )
        assert result == []
        assert any("classify_batch" in e for e in report.errors)

    @pytest.mark.asyncio
    async def test_save_documento_falha_segue_proximo(self) -> None:
        # Storage levanta RuntimeError em save -> orchestrator continua com proximo.
        storage = InMemoryStorage(OWNER)
        report = RunReport(run_id="t", started_at=NOW)

        async def _failing_save(_doc: Documento) -> None:
            msg = "firestore offline"
            raise RuntimeError(msg)

        with patch.object(storage, "save_documento", side_effect=_failing_save):
            items = [_raw("d1")]
            result = await classify_and_store(
                items,
                llm_provider=FakeLLMProvider(),
                storage=storage,
                owner_id=OWNER,
                report=report,
            )
        assert result == []
        assert any("save_documento" in e for e in report.errors)

    @pytest.mark.asyncio
    async def test_llm_providers_exhausted_defere_como_pending(self) -> None:
        # Cenário real cron 24957305420: Gemini 429 + Groq 429 simultâneo.
        # Comportamento esperado: salva itens como PENDING (sem llm) para
        # próxima execução reclassificar — pipeline NÃO derruba.
        class _ExhaustedLLM:
            name = "gemini+groq"

            async def classify_batch(
                self, _items_text: list[str], *, system_prompt: str | None = None
            ) -> list[dict[str, Any]]:
                msg = "Both LLM providers exhausted: gemini, groq"
                raise LLMProvidersExhaustedError(msg)

        storage = InMemoryStorage(OWNER)
        report = RunReport(run_id="t", started_at=NOW)
        items = [_raw("d1"), _raw("d2")]
        result = await classify_and_store(
            items,
            llm_provider=_ExhaustedLLM(),
            storage=storage,
            owner_id=OWNER,
            report=report,
        )
        # Resultado: nenhum doc CLASSIFIED (lista de retorno vazia)
        assert result == []
        # Mas itens foram salvos como PENDING para reclassificar depois
        assert report.items_stored == 2
        assert any("classify_deferred" in e for e in report.errors)
        # Verifica persistência: docs existem com llm=None e status PENDING
        all_docs = await storage.list_documentos(limit=10)
        assert len(all_docs) == 2
        assert all(d.llm is None for d in all_docs)
        assert all(d.status == StatusDocumento.PENDING for d in all_docs)

    @pytest.mark.asyncio
    async def test_llm_exhausted_save_falha_continua_pipeline(self) -> None:
        # Cobre branch save_deferred_failed: storage também falha durante defer.
        # Pipeline continua para próximo batch.
        class _ExhaustedLLM:
            name = "gemini+groq"

            async def classify_batch(
                self, _items_text: list[str], *, system_prompt: str | None = None
            ) -> list[dict[str, Any]]:
                raise LLMProvidersExhaustedError("both exhausted")

        storage = InMemoryStorage(OWNER)
        report = RunReport(run_id="t", started_at=NOW)

        async def _failing_save(_doc: Documento) -> None:
            raise RuntimeError("firestore offline during defer")

        with patch.object(storage, "save_documento", side_effect=_failing_save):
            items = [_raw("d1")]
            result = await classify_and_store(
                items,
                llm_provider=_ExhaustedLLM(),
                storage=storage,
                owner_id=OWNER,
                report=report,
            )
        assert result == []
        # report.errors registra o defer; save_deferred_failed vai pro log
        assert any("classify_deferred" in e for e in report.errors)


@pytest.mark.integration
class TestReprocessErrorPaths:
    @pytest.mark.asyncio
    async def test_reprocess_classify_falha_continua(self) -> None:
        storage = InMemoryStorage(OWNER)
        await _save_all(storage, [_make_doc("d1")])

        class _FailingLLM:
            name = "failing"

            async def classify_batch(
                self, items_text: list[str], *, system_prompt: str | None = None
            ) -> list[dict[str, Any]]:
                msg = "timeout"
                raise TimeoutError(msg)

        report = await reprocess_documents(
            storage=storage,
            llm_provider=_FailingLLM(),
            limit=10,
        )
        # Erro registrado mas pipeline nao quebra
        assert any("reprocess_classify" in e for e in report.errors)
        assert report.items_classified == 0

    @pytest.mark.asyncio
    async def test_reprocess_update_falha_continua(self) -> None:
        storage = InMemoryStorage(OWNER)
        await _save_all(storage, [_make_doc("d1")])

        async def _failing_update(_doc_id: str, _llm: LLMResult) -> None:
            msg = "no doc"
            raise ValueError(msg)

        with patch.object(storage, "update_llm", side_effect=_failing_update):
            report = await reprocess_documents(
                storage=storage,
                llm_provider=FakeLLMProvider(),
                limit=10,
            )
        # update_llm falhou, mas o batch nao foi creditado
        assert report.items_classified == 0


@pytest.mark.integration
class TestNotifyErrorPaths:
    @pytest.mark.asyncio
    async def test_critico_falha_em_send_nao_quebra(self) -> None:
        # Telegram retorna 500 em CRITICO -> exception capturada
        storage = InMemoryStorage(OWNER)
        doc = _make_doc("d1", tier=SeverityTier.CRITICO)
        await _save_all(storage, [doc])
        report = RunReport(run_id="t", started_at=NOW)

        # Patch TelegramNotifier.send_digest para levantar erro
        # (orchestrator usa send_digest mesmo para CRITICO; ver linha 338 do orchestrator)
        from monitoritcd.notifiers import telegram_notifier as _tg_mod  # noqa: PLC0415

        async def _boom(*_args: object, **_kwargs: object) -> None:
            msg = "telegram down"
            raise RuntimeError(msg)

        with patch.object(_tg_mod.TelegramNotifier, "send_digest", _boom):
            await notify_documents(
                [doc],
                settings=_settings(),
                storage=storage,
                report=report,
            )
        assert any("notify_critico" in e for e in report.errors)

    @pytest.mark.asyncio
    async def test_digest_status_update_falha_nao_quebra(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Após digest, update_status falha -> warning, mas pipeline continua.
        storage = InMemoryStorage(OWNER)
        doc = _make_doc("d1", tier=SeverityTier.NORMAL)
        await _save_all(storage, [doc])
        report = RunReport(run_id="t", started_at=NOW)

        from monitoritcd.notifiers import email_notifier as _email_mod  # noqa: PLC0415

        async def _fake_send_digest(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        monkeypatch.setattr(_email_mod.EmailNotifier, "send_digest", _fake_send_digest)

        async def _failing_update_status(_doc_id: str, _status: StatusDocumento) -> None:
            msg = "doc moved"
            raise ValueError(msg)

        async with respx.mock:
            respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
                return_value=httpx.Response(200, json={"ok": True}),
            )
            with patch.object(storage, "update_status", side_effect=_failing_update_status):
                await notify_documents(
                    [doc],
                    settings=_settings(),
                    storage=storage,
                    report=report,
                )
        # Notificacao foi enviada (telegram + email contadores)
        assert report.items_notified_telegram == 1
        assert report.items_notified_email == 1


@pytest.mark.integration
class TestPingHealthcheckErrorPath:
    @pytest.mark.asyncio
    async def test_http_error_silencioso(self) -> None:
        # Healthcheck timeout/ConnectError -> warning silencioso (linhas 403-404)
        url = "https://hc-ping.com/abc-def"
        async with respx.mock:
            respx.get(url).mock(side_effect=httpx.ConnectError("offline"))
            await ping_healthcheck(_settings(healthcheck_url=url), success=True)
        # Sem assert: o ponto e' que nao levanta

    @pytest.mark.asyncio
    async def test_failure_path_acrescenta_fail(self) -> None:
        # success=False -> URL final tem /fail
        url = "https://hc-ping.com/abc-def"
        async with respx.mock:
            route = respx.get(url + "/fail").mock(
                return_value=httpx.Response(200),
            )
            await ping_healthcheck(_settings(healthcheck_url=url), success=False)
        assert route.called


@pytest.mark.integration
class TestRunPipelineAuditError:
    @pytest.mark.asyncio
    async def test_audit_append_falha_nao_quebra_run(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Audit failure no final do pipeline -> warning, run completa.
        from monitoritcd.orchestrator import run_pipeline  # noqa: PLC0415
        from monitoritcd.storage.audit_log import AuditLog  # noqa: PLC0415

        # sources_dir vazio simplifica: pipeline roda sem fontes
        sources_dir = tmp_path  # type: ignore[assignment]

        # Mock audit.append para levantar
        async def _failing_append(**_kwargs: object) -> None:
            msg = "audit corrupted"
            raise RuntimeError(msg)

        monkeypatch.setattr(AuditLog, "append", AsyncMock(side_effect=_failing_append))

        storage = InMemoryStorage(OWNER)
        report = await run_pipeline(
            sources_dir=sources_dir,  # type: ignore[arg-type]
            settings=_settings(),
            storage=storage,
            llm_provider=FakeLLMProvider(),
            notify=False,
        )
        # Pipeline completou apesar do audit falhar
        assert report.finished_at is not None
