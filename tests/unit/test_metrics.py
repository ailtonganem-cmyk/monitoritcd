"""Testes do módulo metrics (Categoria 11 IDEAS.md)."""

from __future__ import annotations

import json

import pytest

from monitoritcd.metrics import (
    ExecutionMetrics,
    get_memory_peak_mb,
    to_json_feed,
    to_prometheus,
)


@pytest.mark.unit
class TestExecutionMetrics:
    def test_volumes_basicos(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.items_collected = 100
        m.items_classified = 50
        m.items_discarded = 40
        m.items_notified = 10
        d = m.to_dict()
        assert d["items"]["collected"] == 100
        assert d["items"]["notified"] == 10

    def test_record_collector(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.record_collector("alesp", duration_ms=120, items=5, errors=0)
        m.record_collector("falha", duration_ms=50, items=0, errors=1)
        assert m.collector_durations_ms["alesp"] == 120
        assert m.collector_errors["falha"] == 1
        assert "alesp" not in m.collector_errors  # zero errors → não registra

    def test_record_llm(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.record_llm(tokens=500)
        m.record_llm(tokens=300, success=False)
        assert m.llm_calls == 2
        assert m.llm_tokens_consumed == 800
        assert m.llm_failures == 1

    def test_record_uf(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.record_uf("SP")
        m.record_uf("SP")  # idempotente (set)
        m.record_uf("RJ")
        assert m.ufs_with_items == {"SP", "RJ"}

    def test_quota_pct(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.firestore_writes = 10_000
        # 10K / 20K = 50%
        assert m.quota_pct_firestore_writes() == 50.0

    def test_quota_capped_at_100(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.firestore_writes = 100_000
        assert m.quota_pct_firestore_writes() == 100.0

    def test_quota_gemini(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.llm_calls = 750
        # 750 / 1500 = 50%
        assert m.quota_pct_gemini() == 50.0

    def test_finish_idempotente(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.finish()
        first = m.finished_at
        m.finish()
        assert m.finished_at == first

    def test_time_stage_context_manager(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        with m.time_stage("collect"):
            pass
        assert "collect" in m.stage_durations_ms
        assert m.stage_durations_ms["collect"] >= 0


@pytest.mark.unit
class TestPrometheus:
    def test_export_format(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.items_collected = 5
        m.llm_calls = 3
        m.firestore_writes = 100
        m.record_uf("SP")
        m.record_collector("alesp", duration_ms=100, items=5)
        result = to_prometheus(m)
        # Formato Prometheus
        assert "# HELP" in result
        assert "# TYPE" in result
        assert "monitoritcd_items_total" in result
        assert 'stage="collected"' in result
        assert "monitoritcd_collector_duration_ms" in result
        assert 'source="alesp"' in result


@pytest.mark.unit
class TestJSONFeed:
    def test_valid_json(self) -> None:
        m = ExecutionMetrics(run_id="r1")
        m.items_collected = 5
        result = to_json_feed(m)
        data = json.loads(result)
        assert data["run_id"] == "r1"
        assert data["items"]["collected"] == 5


@pytest.mark.unit
class TestMemoryPeak:
    def test_returns_float(self) -> None:
        # Best-effort; pode ser 0.0 se psutil não estiver disponível
        result = get_memory_peak_mb()
        assert isinstance(result, float)
        assert result >= 0
