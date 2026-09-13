"""Saúde por execução de fonte — zeros consecutivos (issue #38).

Complementa Healthchecks.io (ping global) e o heartbeat in-memory.
Não mistura com `source_health.py` (score / auto-disable por exceção).
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — pydantic precisa em runtime
from typing import TYPE_CHECKING, Annotated

from pydantic import Field

from monitoritcd.core import limits
from monitoritcd.core.models import OwnerScoped, SourceId

if TYPE_CHECKING:
    from monitoritcd.core.models import Source


class SourceRunHealth(OwnerScoped):
    """Documento em `monitor_source_health/{source_id}`."""

    source_id: SourceId
    last_nonzero_at: datetime | None = None
    consecutive_zero_runs: Annotated[int, Field(ge=0, le=limits.MAX_CONSECUTIVE_ZERO_RUNS)] = 0
    last_run_at: datetime
    last_items_count: Annotated[int, Field(ge=0, le=limits.MAX_LAST_ITEMS_COUNT)] = 0


def effective_expected_min_items(source: Source) -> int | None:
    """Valor efetivo que liga o alerta de zeros consecutivos.

    Campo explícito prevalece. `fragile: true` sem campo ⇒ 1. `0` ⇒ opt-out.
    """
    if source.expected_min_items_per_week is not None:
        return source.expected_min_items_per_week
    if source.fragile:
        return limits.DEFAULT_FRAGILE_EXPECTED_MIN_ITEMS_PER_WEEK
    return None


def apply_run_counts(
    previous: SourceRunHealth | None,
    *,
    source_id: str,
    owner_id: str,
    items_count: int,
    now: datetime,
    alert_threshold: int = limits.DEFAULT_ZERO_RUN_ALERT_THRESHOLD,
) -> tuple[SourceRunHealth, bool]:
    """Aplica o resultado de uma run. `alert_now` só no cruzamento do limiar."""
    stored_count = max(0, min(items_count, limits.MAX_LAST_ITEMS_COUNT))
    if items_count > 0:
        updated = SourceRunHealth(
            owner_id=owner_id,
            source_id=source_id,
            last_nonzero_at=now,
            consecutive_zero_runs=0,
            last_run_at=now,
            last_items_count=stored_count,
        )
        return updated, False

    previous_zeros = previous.consecutive_zero_runs if previous is not None else 0
    consecutive = min(previous_zeros + 1, limits.MAX_CONSECUTIVE_ZERO_RUNS)
    last_nonzero = previous.last_nonzero_at if previous is not None else None
    updated = SourceRunHealth(
        owner_id=owner_id,
        source_id=source_id,
        last_nonzero_at=last_nonzero,
        consecutive_zero_runs=consecutive,
        last_run_at=now,
        last_items_count=0,
    )
    alert_now = consecutive == alert_threshold
    return updated, alert_now


__all__ = [
    "SourceRunHealth",
    "apply_run_counts",
    "effective_expected_min_items",
]
