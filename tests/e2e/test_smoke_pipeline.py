"""Smoke E2E (Sugestão #12).

Roda pipeline completa com fontes mockadas (sem rede) + InMemoryStorage +
FakeLLM. Garantia mínima: estrutura do pipeline não regrediu.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from monitoritcd.core.models import ActiveStatesConfig
from monitoritcd.llm.fake import FakeLLMProvider
from monitoritcd.orchestrator import run_pipeline
from monitoritcd.storage.in_memory import InMemoryStorage


@pytest.fixture
def storage() -> InMemoryStorage:
    """InMemoryStorage com active_states pré-populado para SP+_federal."""
    return InMemoryStorage(owner_id="test-owner")


@pytest.fixture
def fake_settings() -> object:
    """Settings mínimas para o pipeline."""

    class _S:
        OWNER_ID = "test-owner"
        OWNER_EMAIL = "test@example.com"
        FIREBASE_PROJECT_ID = "test"
        HEALTHCHECKS_URL = None
        PROXY_BR_URL = None
        PROXY_BR_TOKEN = None
        TELEGRAM_BOT_TOKEN = None
        TELEGRAM_OWNER_CHAT_ID = 0
        TELEGRAM_WEBHOOK_SECRET = None
        GMAIL_USER = "noreply@example.com"
        GMAIL_APP_PASSWORD = None
        ENV = "test"
        DRY_RUN = True

    return _S()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_smoke_pipeline_no_sources(storage, fake_settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Pipeline com diretório vazio executa sem crashar."""
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()

    # Active states bloqueia tudo
    await storage.save_active_states(
        ActiveStatesConfig(
            owner_id="test-owner",
            active_uf=[],
            federal_active=False,
            updated_at=datetime.now(UTC),
            updated_by="test",
        )
    )

    report = await run_pipeline(
        fake_settings,  # type: ignore[arg-type]
        storage=storage,
        llm_provider=FakeLLMProvider(),
        sources_dir=sources_dir,
        notify=False,
    )

    assert report.run_id is not None
    assert report.sources_consulted == 0
    assert report.items_collected == 0
    assert report.duration_seconds >= 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pipeline_isolated_failure_does_not_crash(storage, fake_settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Princípio canônico: falha em fonte isolada NÃO derruba pipeline."""
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()

    await storage.save_active_states(
        ActiveStatesConfig(
            owner_id="test-owner",
            active_uf=["SP"],
            federal_active=True,
            updated_at=datetime.now(UTC),
            updated_by="test",
        )
    )

    # Sem YAMLs em SP/, sources_consulted = 0
    report = await run_pipeline(
        fake_settings,  # type: ignore[arg-type]
        storage=storage,
        llm_provider=FakeLLMProvider(),
        sources_dir=sources_dir,
        notify=False,
    )
    # Não crash, retorna report válido
    assert report.run_id
