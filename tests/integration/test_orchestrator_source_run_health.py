"""Smoke do orquestrador: zeros consecutivos, opt-in e anti-spam (issue #38)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — usado em runtime nos fixtures
from textwrap import dedent
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from monitoritcd.core import limits
from monitoritcd.core.config import Settings
from monitoritcd.core.models import ActiveStatesConfig, RawItem, Source
from monitoritcd.llm.fake import FakeLLMProvider
from monitoritcd.observability.source_run_health import SourceRunHealth
from monitoritcd.orchestrator import _format_zero_run_alert, run_pipeline
from monitoritcd.storage import InMemoryStorage

NOW = datetime(2026, 9, 13, tzinfo=UTC)
OWNER = "owner-test"
N = limits.DEFAULT_ZERO_RUN_ALERT_THRESHOLD


def _settings() -> Settings:
    return Settings(
        OWNER_ID=OWNER,
        OWNER_EMAIL="o@example.com",
        GEMINI_API_KEY=SecretStr("g"),
        GMAIL_USER="b@example.com",
        GMAIL_APP_PASSWORD=SecretStr("p"),
        TELEGRAM_BOT_TOKEN=SecretStr("t"),
        TELEGRAM_OWNER_CHAT_ID=1,
        TELEGRAM_WEBHOOK_SECRET=SecretStr("ws"),
        FIREBASE_PROJECT_ID="p",
        FIREBASE_STORAGE_BUCKET="p.appspot.com",
        FIREBASE_SERVICE_ACCOUNT_JSON=SecretStr("{}"),
        HEALTHCHECKS_URL=None,
    )


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content), encoding="utf-8")


@dataclass
class _FakeTelegram:
    sent: list[str] = field(default_factory=list)

    async def __aenter__(self) -> _FakeTelegram:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def send_message(self, text: str, **_kwargs: Any) -> int:
        self.sent.append(text)
        return 1

    async def send_digest(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _patch_telegram(monkeypatch: pytest.MonkeyPatch) -> _FakeTelegram:
    fake = _FakeTelegram()
    monkeypatch.setattr("monitoritcd.orchestrator.TelegramNotifier", lambda *_a, **_k: fake)
    return fake


async def _empty_collect(_source: Source, **_kwargs: object) -> list[RawItem]:
    return []


async def _one_item(source: Source, **_kwargs: object) -> list[RawItem]:
    return [
        RawItem(
            source_id=source.id,
            titulo_raw="ITCMD item",
            url="https://example.gov.br/i",
            fetched_at=NOW,
            content_hash="a" * 64,
        )
    ]


async def _boom(_source: Source, **_kwargs: object) -> list[RawItem]:
    msg = "fonte indisponivel"
    raise RuntimeError(msg)


async def _run(
    sources_dir: Path,
    storage: InMemoryStorage,
    *,
    notify: bool = True,
) -> None:
    await run_pipeline(
        _settings(),
        storage=storage,
        llm_provider=FakeLLMProvider(),
        sources_dir=sources_dir,
        notify=notify,
    )


@pytest.fixture
def fragile_dir(tmp_path: Path) -> Path:
    _write_yaml(
        tmp_path / "_federal" / "fragile-fed.yaml",
        """\
        id: fragile-fed
        uf: _federal
        nome: "Fake fragile"
        tipo: noticia
        parser: generic_rss
        url: "https://www.example.gov.br/feed.xml"
        keywords_required:
          - ITCMD
        ativo: true
        fragile: true
        """,
    )
    return tmp_path


@pytest.fixture
def quiet_dir(tmp_path: Path) -> Path:
    _write_yaml(
        tmp_path / "_federal" / "quiet-fed.yaml",
        """\
        id: quiet-fed
        uf: _federal
        nome: "Fake quiet"
        tipo: noticia
        parser: generic_rss
        url: "https://www.example.gov.br/feed.xml"
        keywords_required:
          - ITCMD
        ativo: true
        """,
    )
    return tmp_path


@pytest.mark.integration
class TestFormatZeroRunAlert:
    def test_escapa_underscore_no_source_id(self) -> None:
        health = SourceRunHealth(
            owner_id=OWNER,
            source_id="mg_doe",
            last_run_at=NOW,
            consecutive_zero_runs=7,
        )
        text = _format_zero_run_alert(health)
        assert "mg\\_doe" in text
        assert "🟠" in text
        assert "ALTA" in text
        assert "nunca" in text


@pytest.mark.integration
class TestRunPipelineSourceRunHealth:
    @pytest.mark.asyncio
    async def test_n_zeros_dispara_uma_vez(
        self,
        fragile_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _empty_collect)
        fake_tg = _patch_telegram(monkeypatch)
        storage = InMemoryStorage(OWNER)

        for i in range(N - 1):
            await _run(fragile_dir, storage)
            assert fake_tg.sent == []
            health = await storage.get_source_run_health("fragile-fed")
            assert health is not None
            assert health.consecutive_zero_runs == i + 1

        await _run(fragile_dir, storage)
        assert len(fake_tg.sent) == 1
        assert "fragile\\-fed" in fake_tg.sent[0] or "fragile-fed" in fake_tg.sent[0]

        await _run(fragile_dir, storage)
        assert len(fake_tg.sent) == 1
        health = await storage.get_source_run_health("fragile-fed")
        assert health is not None
        assert health.consecutive_zero_runs == N + 1

    @pytest.mark.asyncio
    async def test_intercalado_nao_alerta(
        self,
        fragile_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_tg = _patch_telegram(monkeypatch)
        storage = InMemoryStorage(OWNER)

        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _empty_collect)
        await _run(fragile_dir, storage)
        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _one_item)
        await _run(fragile_dir, storage)
        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _empty_collect)
        await _run(fragile_dir, storage)

        assert fake_tg.sent == []
        health = await storage.get_source_run_health("fragile-fed")
        assert health is not None
        assert health.consecutive_zero_runs == 1
        assert health.last_nonzero_at is not None

    @pytest.mark.asyncio
    async def test_nao_opt_in_persiste_sem_alerta(
        self,
        quiet_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _empty_collect)
        fake_tg = _patch_telegram(monkeypatch)
        storage = InMemoryStorage(OWNER)
        for _ in range(N):
            await _run(quiet_dir, storage)
        assert fake_tg.sent == []
        health = await storage.get_source_run_health("quiet-fed")
        assert health is not None
        assert health.consecutive_zero_runs == N

    @pytest.mark.asyncio
    async def test_excecao_conta_como_zero(
        self,
        fragile_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _boom)
        fake_tg = _patch_telegram(monkeypatch)
        storage = InMemoryStorage(OWNER)
        for _ in range(N):
            await _run(fragile_dir, storage)
        assert len(fake_tg.sent) == 1
        health = await storage.get_source_run_health("fragile-fed")
        assert health is not None
        assert health.consecutive_zero_runs == N
        assert health.last_items_count == 0

    @pytest.mark.asyncio
    async def test_notify_false_nao_chama_telegram(
        self,
        fragile_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _empty_collect)
        fake_tg = _patch_telegram(monkeypatch)
        storage = InMemoryStorage(OWNER)
        for _ in range(N):
            await _run(fragile_dir, storage, notify=False)
        assert fake_tg.sent == []
        health = await storage.get_source_run_health("fragile-fed")
        assert health is not None
        assert health.consecutive_zero_runs == N

    @pytest.mark.asyncio
    async def test_fonte_pulada_nao_atualiza(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write_yaml(
            tmp_path / "SP" / "fake-sp.yaml",
            """\
            id: fake-sp
            uf: SP
            nome: "Fake SP"
            tipo: sefaz
            parser: generic_rss
            url: "https://www.example.gov.br/feed-sp.xml"
            ativo: true
            fragile: true
            """,
        )
        _write_yaml(
            tmp_path / "_federal" / "fragile-fed.yaml",
            """\
            id: fragile-fed
            uf: _federal
            nome: "Fake fragile"
            tipo: noticia
            parser: generic_rss
            url: "https://www.example.gov.br/feed.xml"
            ativo: true
            fragile: true
            """,
        )
        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _empty_collect)
        _patch_telegram(monkeypatch)
        storage = InMemoryStorage(OWNER)
        await storage.save_active_states(
            ActiveStatesConfig(
                owner_id=OWNER,
                active_uf=["MG"],
                federal_active=True,
                updated_at=NOW,
                updated_by="test",
            )
        )
        await _run(tmp_path, storage)
        assert await storage.get_source_run_health("fragile-fed") is not None
        assert await storage.get_source_run_health("fake-sp") is None

    @pytest.mark.asyncio
    async def test_falha_de_storage_nao_derruba_run(
        self,
        fragile_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("monitoritcd.orchestrator.collect_from_source", _empty_collect)
        _patch_telegram(monkeypatch)
        storage = InMemoryStorage(OWNER)
        storage.get_source_run_health = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("firestore indisponivel")
        )
        report = await run_pipeline(
            _settings(),
            storage=storage,
            llm_provider=FakeLLMProvider(),
            sources_dir=fragile_dir,
            notify=False,
        )
        assert report.finished_at is not None
        assert any("source_run_health" in e for e in report.errors)
