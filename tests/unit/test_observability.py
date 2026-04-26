"""Testes do subsistema de observabilidade (Sugestões #27, #31, #32)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from monitoritcd.observability.dlq import DeadLetterQueue, DLQEntry
from monitoritcd.observability.prometheus_textfile import emit_run_metrics, write_metrics
from monitoritcd.observability.source_heartbeat import SourceHeartbeat

if TYPE_CHECKING:
    from pathlib import Path

# ── Prometheus textfile ────────────────────────────────────────────────────


@pytest.mark.unit
def test_write_metrics_basic(tmp_path: Path) -> None:
    """write_metrics produz formato textfile válido."""
    out = tmp_path / "test.prom"
    write_metrics(
        out,
        {
            "test_metric": {
                "type": "gauge",
                "help": "Test",
                "value": 42,
            }
        },
    )
    text = out.read_text(encoding="utf-8")
    assert "# HELP test_metric Test" in text
    assert "# TYPE test_metric gauge" in text
    assert "test_metric 42" in text


@pytest.mark.unit
def test_write_metrics_with_labels(tmp_path: Path) -> None:
    """Labels são formatadas corretamente."""
    out = tmp_path / "test.prom"
    write_metrics(
        out,
        {
            "items": {
                "type": "counter",
                "help": "Items",
                "value": 10,
                "labels": {"uf": "SP", "tipo": "lei"},
            }
        },
    )
    text = out.read_text(encoding="utf-8")
    assert 'items{tipo="lei",uf="SP"} 10' in text


@pytest.mark.unit
def test_emit_run_metrics_writes_all(tmp_path: Path) -> None:
    """emit_run_metrics produz todas as métricas esperadas."""
    out = tmp_path / "run.prom"
    emit_run_metrics(
        out,
        items_collected=100,
        items_classified=80,
        items_stored=70,
        sources_consulted=14,
        sources_failed=1,
        duration_seconds=120.5,
    )
    text = out.read_text(encoding="utf-8")
    assert "monitoritcd_items_collected 100" in text
    assert "monitoritcd_items_classified 80" in text
    assert "monitoritcd_items_stored 70" in text
    assert "monitoritcd_run_duration_seconds 120.5" in text


@pytest.mark.unit
def test_atomic_write(tmp_path: Path) -> None:
    """Escrita usa rename atômico (não há .tmp ao final)."""
    out = tmp_path / "atomic.prom"
    write_metrics(out, {"x": {"type": "gauge", "help": "x", "value": 1}})
    assert out.exists()
    assert not (out.parent / (out.name + ".tmp")).exists()


# ── DLQ ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_dlq_enqueue_and_list() -> None:
    """DLQ armazena e lista entries."""
    dlq = DeadLetterQueue()
    entry = DLQEntry.create(
        entry_id="x1",
        reason="classify_quota_exhausted",
        attempt_count=3,
        payload={"doc_id": "abc"},
        error_message="quota",
    )
    dlq.enqueue(entry)
    assert len(dlq) == 1
    assert dlq.list_all() == [entry]


@pytest.mark.unit
def test_dlq_filter_by_reason() -> None:
    dlq = DeadLetterQueue()
    dlq.enqueue(
        DLQEntry.create(
            entry_id="x1",
            reason="classify_quota_exhausted",
            attempt_count=3,
            payload={},
            error_message="",
        )
    )
    dlq.enqueue(
        DLQEntry.create(
            entry_id="x2",
            reason="notify_telegram_failed",
            attempt_count=3,
            payload={},
            error_message="",
        )
    )
    only_classify = dlq.list_by_reason("classify_quota_exhausted")
    assert len(only_classify) == 1
    assert only_classify[0].entry_id == "x1"


@pytest.mark.unit
def test_dlq_remove() -> None:
    dlq = DeadLetterQueue()
    dlq.enqueue(
        DLQEntry.create(
            entry_id="x1",
            reason="classify_quota_exhausted",
            attempt_count=3,
            payload={},
            error_message="",
        )
    )
    removed_x1 = dlq.remove("x1")
    removed_missing = dlq.remove("nonexistent")
    assert removed_x1 is True
    assert removed_missing is False
    assert len(dlq) == 0


# ── SourceHeartbeat ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_heartbeat_success_resets_failures() -> None:
    hb = SourceHeartbeat()
    hb.record_failure("src1")
    hb.record_failure("src1")
    assert hb.consecutive_failures["src1"] == 2
    hb.record_success("src1")
    assert hb.consecutive_failures["src1"] == 0


@pytest.mark.unit
def test_stale_sources_detection() -> None:
    hb = SourceHeartbeat()
    now = datetime.now(UTC)
    # Fonte ok recentemente
    hb.record_success("fresh", now=now - timedelta(hours=1))
    # Fonte stale (10 dias)
    hb.record_success("stale", now=now - timedelta(days=10))

    stale = hb.stale_sources(threshold=timedelta(days=7), now=now)
    assert "stale" in stale
    assert "fresh" not in stale


@pytest.mark.unit
def test_chronically_failing() -> None:
    hb = SourceHeartbeat()
    for _ in range(6):
        hb.record_failure("broken")
    hb.record_failure("once")
    chronic = hb.chronically_failing(min_consecutive=5)
    assert "broken" in chronic
    assert "once" not in chronic


@pytest.mark.unit
def test_heartbeat_singleton_helpers() -> None:
    """get_heartbeat retorna singleton; helpers atualizam estado global."""
    from monitoritcd.observability import source_heartbeat as sh  # noqa: PLC0415
    from monitoritcd.observability.source_heartbeat import (  # noqa: PLC0415
        get_heartbeat,
        record_source_failure,
        record_source_success,
    )

    # Reset singleton para isolamento de teste
    sh._heartbeat = None

    hb1 = get_heartbeat()
    hb2 = get_heartbeat()
    assert hb1 is hb2  # singleton

    record_source_failure("src-test")
    record_source_failure("src-test")
    assert hb1.consecutive_failures["src-test"] == 2

    record_source_success("src-test")
    assert hb1.consecutive_failures["src-test"] == 0

    # Cleanup
    sh._heartbeat = None


@pytest.mark.unit
def test_heartbeat_uses_now_default() -> None:
    """record_success/failure aceitam now opcional."""
    hb = SourceHeartbeat()
    hb.record_success("src-default-time")
    assert "src-default-time" in hb.last_success
    hb.record_failure("src-fail-default-time")
    assert "src-fail-default-time" in hb.last_failure
