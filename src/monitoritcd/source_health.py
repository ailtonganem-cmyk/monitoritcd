"""Gestão de saúde de fontes (Categoria 12 IDEAS.md).

Cobre:
- #369 auto-disable após N falhas
- #370 auto-reativação ao voltar a funcionar
- #371 health score (success rate + freshness)
- #379 anotação "última revisão manual"
- #386 métrica "novidades por mês" por fonte
- #387 métrica "false positives" (descartados LLM) por fonte

Lint específico (#368) está em `source_validators.py`.
URL discovery (#374, #389, #390) está em `source_discovery.py`.

Princípios canônicos:
- Princípio 2: limites duros em janelas de avaliação
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import Documento

DEFAULT_FAILURE_THRESHOLD: Final[int] = 5  # falhas seguidas antes de auto-disable
DEFAULT_RECOVERY_THRESHOLD: Final[int] = 3  # sucessos seguidos para reativar
DEFAULT_HEALTH_WINDOW_DAYS: Final[int] = 30


def health_score(
    docs: Sequence[Documento],
    source_id: str,
    *,
    days: int = DEFAULT_HEALTH_WINDOW_DAYS,
) -> dict[str, float]:
    """#371 — Health score por fonte (success_rate + freshness).

    Args:
        docs: documentos coletados.
        source_id: ID da fonte a avaliar.
        days: janela de avaliação.

    Returns:
        Dict com keys: items_count, freshness_days, success_rate (0-1).
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)
    relevant = [
        d
        for d in docs
        if d.source.id == source_id
        and (
            d.original.fetched_at.replace(tzinfo=UTC)
            if d.original.fetched_at.tzinfo is None
            else d.original.fetched_at
        )
        >= cutoff
    ]
    if not relevant:
        return {"items_count": 0, "freshness_days": float(days), "success_rate": 0.0}

    # Freshness: idade média
    ages = []
    for d in relevant:
        dt = d.original.data_publicacao or d.original.fetched_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        ages.append((now - dt).total_seconds() / 86400)
    avg_freshness = sum(ages) / len(ages)

    # Success rate ≈ classificados / coletados
    classified = sum(1 for d in relevant if d.llm is not None)
    rate = classified / len(relevant)

    return {
        "items_count": float(len(relevant)),
        "freshness_days": round(avg_freshness, 1),
        "success_rate": round(rate, 3),
    }


def items_per_month_per_source(
    docs: Sequence[Documento],
) -> dict[str, dict[str, int]]:
    """#386 — Conta novidades por (fonte, mês YYYY-MM)."""
    result: dict[str, dict[str, int]] = {}
    for d in docs:
        dt = d.original.data_publicacao or d.original.fetched_at
        bucket = f"{dt.year:04d}-{dt.month:02d}"
        per_source = result.setdefault(d.source.id, {})
        per_source[bucket] = per_source.get(bucket, 0) + 1
    return result


def false_positive_rate_per_source(
    docs: Sequence[Documento],
    *,
    relevancia_threshold: int = 5,
) -> dict[str, dict[str, float]]:
    """#387 — Taxa de descartados (relevância < threshold) por fonte.

    Returns:
        Dict source_id → {discarded, total, rate}.
    """
    result: dict[str, dict[str, float]] = {}
    for d in docs:
        if d.llm is None:
            continue
        per = result.setdefault(d.source.id, {"discarded": 0.0, "total": 0.0, "rate": 0.0})
        per["total"] += 1
        if d.llm.relevancia < relevancia_threshold:
            per["discarded"] += 1
    for sid, per in result.items():
        total = per["total"]
        if total > 0:
            per["rate"] = round(per["discarded"] / total, 3)
        _ = sid  # explicit unused-arg suppression
    return result


def should_auto_disable(
    failure_history: Sequence[bool],
    *,
    threshold: int = DEFAULT_FAILURE_THRESHOLD,
) -> bool:
    """#369 — True se as últimas N execuções (boolean fail/success) foram TODAS falhas.

    Args:
        failure_history: lista ordenada cronologicamente, True = sucesso.
        threshold: N falhas seguidas para acionar auto-disable.
    """
    if len(failure_history) < threshold:
        return False
    last_n = failure_history[-threshold:]
    return all(not s for s in last_n)


def should_auto_reactivate(
    success_history: Sequence[bool],
    *,
    threshold: int = DEFAULT_RECOVERY_THRESHOLD,
) -> bool:
    """#370 — True se as últimas N execuções foram TODAS sucesso (após disable)."""
    if len(success_history) < threshold:
        return False
    last_n = success_history[-threshold:]
    return all(s for s in last_n)


def revision_calendar(
    docs: Sequence[Documento],
    *,
    review_period_days: int = 30,
) -> list[tuple[str, int]]:
    """#372 — Lista fontes que devem ser revisadas (sem documentos no período).

    Returns:
        Lista (source_id, days_since_last_doc) ordenada por longevidade desc.
    """
    now = datetime.now(UTC)
    last_seen: dict[str, datetime] = {}
    for d in docs:
        dt = d.original.fetched_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        if d.source.id not in last_seen or last_seen[d.source.id] < dt:
            last_seen[d.source.id] = dt

    candidates: list[tuple[str, int]] = []
    for sid, dt in last_seen.items():
        days_since = (now - dt).days
        if days_since >= review_period_days:
            candidates.append((sid, days_since))
    candidates.sort(key=lambda x: -x[1])
    return candidates


def source_volume_summary(docs: Sequence[Documento]) -> dict[str, int]:
    """Helper: contagem por source_id."""
    return dict(Counter(d.source.id for d in docs))


__all__ = [
    "DEFAULT_FAILURE_THRESHOLD",
    "DEFAULT_HEALTH_WINDOW_DAYS",
    "DEFAULT_RECOVERY_THRESHOLD",
    "false_positive_rate_per_source",
    "health_score",
    "items_per_month_per_source",
    "revision_calendar",
    "should_auto_disable",
    "should_auto_reactivate",
    "source_volume_summary",
]
