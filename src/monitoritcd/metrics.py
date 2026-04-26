"""Coletor de métricas de execução e exportador Prometheus (#341-#358 IDEAS.md).

Cobre:
- #341-#346 métricas de coletor (volume, erro, tempo)
- #347-#349 quota tracking (LLM, Firestore, Storage)
- #350-#353 timing e tamanho
- #354 cobertura UF
- #357 export Prometheus textual (sem hosting)
- #358 export JSON Feed

Pré-existente: build_dashboard.py já gera HTML (#355, #356).

Princípios canônicos:
- Princípio 2: contadores limitados a uint64 (sem overflow prático)
- Princípio 3: métricas não contêm secrets
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

DEFAULT_FIRESTORE_FREE_WRITES: Final[int] = 20_000  # Spark plan
DEFAULT_FIRESTORE_FREE_READS: Final[int] = 50_000
DEFAULT_GEMINI_FREE_RPD: Final[int] = 1_500


@dataclass
class ExecutionMetrics:
    """Coleta métricas de uma execução do pipeline.

    Mantida em memória durante a execução; serializada ao final.
    """

    run_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    # Volumes (#341-#344)
    items_collected: int = 0
    items_classified: int = 0
    items_discarded: int = 0
    items_notified: int = 0

    # Por coletor (#345, #346)
    collector_durations_ms: dict[str, float] = field(default_factory=dict)
    collector_errors: dict[str, int] = field(default_factory=dict)
    collector_volumes: dict[str, int] = field(default_factory=dict)

    # LLM (#347)
    llm_tokens_consumed: int = 0
    llm_calls: int = 0
    llm_failures: int = 0

    # Quotas (#348, #349)
    firestore_reads: int = 0
    firestore_writes: int = 0
    storage_bytes: int = 0

    # Pipeline timing (#350, #351, #362)
    classifier_batch_duration_ms: float = 0.0
    notification_duration_ms: float = 0.0
    stage_durations_ms: dict[str, float] = field(default_factory=dict)

    # Por fonte (#352, #353)
    avg_payload_bytes_per_source: dict[str, float] = field(default_factory=dict)
    avg_age_days_per_source: dict[str, float] = field(default_factory=dict)

    # Cobertura (#354)
    ufs_with_items: set[str] = field(default_factory=set)

    # Memória (#363)
    memory_peak_mb: float = 0.0

    @property
    def total_duration_ms(self) -> float:
        """#350 — duração total da execução em ms."""
        end = self.finished_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds() * 1000

    def finish(self) -> None:
        if self.finished_at is None:
            self.finished_at = datetime.now(UTC)

    @contextmanager
    def time_stage(self, stage_name: str) -> Iterator[None]:
        """#362 — context manager para timing de etapa do pipeline."""
        start = time.monotonic()
        try:
            yield
        finally:
            elapsed = (time.monotonic() - start) * 1000
            self.stage_durations_ms[stage_name] = (
                self.stage_durations_ms.get(stage_name, 0) + elapsed
            )

    def record_collector(
        self,
        source_id: str,
        *,
        duration_ms: float,
        items: int,
        errors: int = 0,
    ) -> None:
        self.collector_durations_ms[source_id] = duration_ms
        self.collector_volumes[source_id] = items
        if errors > 0:
            self.collector_errors[source_id] = errors

    def record_llm(self, *, tokens: int, success: bool = True) -> None:
        self.llm_calls += 1
        self.llm_tokens_consumed += tokens
        if not success:
            self.llm_failures += 1

    def record_uf(self, uf: str) -> None:
        self.ufs_with_items.add(uf)

    def quota_pct_firestore_writes(
        self,
        free_quota: int = DEFAULT_FIRESTORE_FREE_WRITES,
    ) -> float:
        """#348 — % do free tier Firestore writes consumido."""
        return min(100.0, (self.firestore_writes / free_quota) * 100)

    def quota_pct_firestore_reads(
        self,
        free_quota: int = DEFAULT_FIRESTORE_FREE_READS,
    ) -> float:
        return min(100.0, (self.firestore_reads / free_quota) * 100)

    def quota_pct_gemini(self, free_rpd: int = DEFAULT_GEMINI_FREE_RPD) -> float:
        """#347/#348 — % do free tier Gemini RPD consumido."""
        return min(100.0, (self.llm_calls / free_rpd) * 100)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_duration_ms": self.total_duration_ms,
            "items": {
                "collected": self.items_collected,
                "classified": self.items_classified,
                "discarded": self.items_discarded,
                "notified": self.items_notified,
            },
            "collectors": {
                "durations_ms": self.collector_durations_ms,
                "errors": self.collector_errors,
                "volumes": self.collector_volumes,
            },
            "llm": {
                "tokens": self.llm_tokens_consumed,
                "calls": self.llm_calls,
                "failures": self.llm_failures,
                "quota_pct_gemini": round(self.quota_pct_gemini(), 2),
            },
            "firestore": {
                "reads": self.firestore_reads,
                "writes": self.firestore_writes,
                "quota_pct_writes": round(self.quota_pct_firestore_writes(), 2),
                "quota_pct_reads": round(self.quota_pct_firestore_reads(), 2),
            },
            "storage_bytes": self.storage_bytes,
            "stage_durations_ms": self.stage_durations_ms,
            "ufs_with_items": sorted(self.ufs_with_items),
            "uf_coverage": len(self.ufs_with_items),
            "memory_peak_mb": self.memory_peak_mb,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Exporters
# ─────────────────────────────────────────────────────────────────────────────


def to_prometheus(metrics: ExecutionMetrics) -> str:
    """#357 — Exporta em formato Prometheus textual (sem servidor)."""
    lines: list[str] = [
        "# HELP monitoritcd_items_total Items processed by stage",
        "# TYPE monitoritcd_items_total counter",
        f'monitoritcd_items_total{{stage="collected"}} {metrics.items_collected}',
        f'monitoritcd_items_total{{stage="classified"}} {metrics.items_classified}',
        f'monitoritcd_items_total{{stage="discarded"}} {metrics.items_discarded}',
        f'monitoritcd_items_total{{stage="notified"}} {metrics.items_notified}',
        "",
        "# HELP monitoritcd_run_duration_ms Duração total da execução",
        "# TYPE monitoritcd_run_duration_ms gauge",
        f"monitoritcd_run_duration_ms {metrics.total_duration_ms}",
        "",
        "# HELP monitoritcd_llm_calls_total Calls ao LLM",
        "# TYPE monitoritcd_llm_calls_total counter",
        f"monitoritcd_llm_calls_total {metrics.llm_calls}",
        f"monitoritcd_llm_failures_total {metrics.llm_failures}",
        f"monitoritcd_llm_tokens_total {metrics.llm_tokens_consumed}",
        "",
        "# HELP monitoritcd_firestore_ops_total Operações Firestore",
        "# TYPE monitoritcd_firestore_ops_total counter",
        f'monitoritcd_firestore_ops_total{{op="reads"}} {metrics.firestore_reads}',
        f'monitoritcd_firestore_ops_total{{op="writes"}} {metrics.firestore_writes}',
        "",
        "# HELP monitoritcd_uf_coverage Cobertura de UFs com items hoje",
        "# TYPE monitoritcd_uf_coverage gauge",
        f"monitoritcd_uf_coverage {len(metrics.ufs_with_items)}",
    ]
    for sid, dur in metrics.collector_durations_ms.items():
        lines.append(f'monitoritcd_collector_duration_ms{{source="{sid}"}} {dur}')
    for sid, errs in metrics.collector_errors.items():
        lines.append(f'monitoritcd_collector_errors_total{{source="{sid}"}} {errs}')
    return "\n".join(lines) + "\n"


def to_json_feed(metrics: ExecutionMetrics) -> str:
    """#358 — Exporta como JSON serializable."""
    return json.dumps(metrics.to_dict(), ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def get_memory_peak_mb() -> float:
    """#363 — Memory peak em MB via psutil (best-effort)."""
    try:
        import psutil  # type: ignore[import-untyped]  # noqa: PLC0415

        process = psutil.Process()
        return float(process.memory_info().rss / 1024 / 1024)
    except (ImportError, OSError):
        return 0.0


__all__ = [
    "DEFAULT_FIRESTORE_FREE_READS",
    "DEFAULT_FIRESTORE_FREE_WRITES",
    "DEFAULT_GEMINI_FREE_RPD",
    "ExecutionMetrics",
    "get_memory_peak_mb",
    "to_json_feed",
    "to_prometheus",
]
