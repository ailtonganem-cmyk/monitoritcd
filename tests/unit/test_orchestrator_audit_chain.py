"""Testes da validação runtime do audit chain (Sugestão #25).

Cobre as 3 ramificações em `orchestrator.run_pipeline`:
- Storage sem `list_audit_recent` → AttributeError silencioso (debug).
- Chain válida → continua sem erro.
- Chain corrompida → registra em `report.errors`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from monitoritcd.core.models import ActiveStatesConfig, AuditLogEntry

if TYPE_CHECKING:
    from pathlib import Path
from monitoritcd.llm.fake import FakeLLMProvider
from monitoritcd.orchestrator import run_pipeline
from monitoritcd.storage.audit_log import AuditLog
from monitoritcd.storage.in_memory import GENESIS_HASH, InMemoryStorage


def _make_settings() -> Any:
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
        RESEND_API_KEY = None
        RESEND_FROM_EMAIL = "noreply@example.com"
        ENV = "test"
        DRY_RUN = True

    return _S()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audit_chain_check_unavailable(tmp_path: Path) -> None:
    """Storage sem list_audit_recent → AttributeError silencioso."""

    class _MinimalStorage(InMemoryStorage):
        async def list_audit_recent(self, limit: int = 20) -> Any:
            raise AttributeError("not supported in this backend")

    storage = _MinimalStorage(owner_id="test-owner")
    await storage.save_active_states(
        ActiveStatesConfig(
            owner_id="test-owner",
            active_uf=[],
            federal_active=False,
            updated_at=datetime.now(UTC),
            updated_by="test",
        )
    )
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()

    report = await run_pipeline(
        _make_settings(),
        storage=storage,
        llm_provider=FakeLLMProvider(),
        sources_dir=sources_dir,
        notify=False,
    )
    # Não deve haver erro no relatório por audit chain
    assert not any("audit_chain" in e for e in report.errors)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audit_chain_valid_check(tmp_path: Path) -> None:
    """Chain válida (entries reais no storage) passa pelo check sem erro."""
    storage = InMemoryStorage(owner_id="test-owner")
    audit = AuditLog(storage)
    # Adiciona entries válidas
    await audit.append(actor="test", action="t1", payload={"x": 1})
    await audit.append(actor="test", action="t2", payload={"y": 2})
    await storage.save_active_states(
        ActiveStatesConfig(
            owner_id="test-owner",
            active_uf=[],
            federal_active=False,
            updated_at=datetime.now(UTC),
            updated_by="test",
        )
    )
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()

    report = await run_pipeline(
        _make_settings(),
        storage=storage,
        llm_provider=FakeLLMProvider(),
        sources_dir=sources_dir,
        notify=False,
    )
    # Não há erro
    assert not any("audit_chain_corruption" in e for e in report.errors)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audit_chain_corrupted_detected(tmp_path: Path) -> None:
    """Chain corrompida em runtime → erro no relatório."""

    class _CorruptedAuditStorage(InMemoryStorage):
        async def list_audit_recent(self, limit: int = 20) -> list[AuditLogEntry]:
            # Retorna entry com prev_hash inválido
            now = datetime.now(UTC)
            return [
                AuditLogEntry(
                    owner_id="test-owner",
                    entry_id="bogus",
                    timestamp=now,
                    actor="evil",
                    action="tampered",
                    payload_hash="b" * 64,
                    prev_hash="z" * 64,  # Inválido — esperado GENESIS_HASH
                    result="success",
                )
            ]

    storage = _CorruptedAuditStorage(owner_id="test-owner")
    await storage.save_active_states(
        ActiveStatesConfig(
            owner_id="test-owner",
            active_uf=[],
            federal_active=False,
            updated_at=datetime.now(UTC),
            updated_by="test",
        )
    )
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()

    report = await run_pipeline(
        _make_settings(),
        storage=storage,
        llm_provider=FakeLLMProvider(),
        sources_dir=sources_dir,
        notify=False,
    )
    # GENESIS_HASH != "z" * 64 — chain quebrada
    assert any("audit_chain_corruption" in e for e in report.errors), (
        f"Esperava audit_chain_corruption em errors, recebido: {report.errors}. "
        f"GENESIS={GENESIS_HASH[:16]}..."
    )
