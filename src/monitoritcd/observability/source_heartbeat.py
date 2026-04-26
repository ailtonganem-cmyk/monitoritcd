"""Heartbeat per-source (Sugestão #32).

Mantém em memória `last_success_at` por fonte. Bot `/status` consulta isso
para flagar fontes silenciosamente quebradas há > 7 dias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class SourceHeartbeat:
    """Tracking de heartbeats por fonte."""

    last_success: dict[str, datetime] = field(default_factory=dict)
    last_failure: dict[str, datetime] = field(default_factory=dict)
    consecutive_failures: dict[str, int] = field(default_factory=dict)

    def record_success(self, source_id: str, *, now: datetime | None = None) -> None:
        """Marca fonte como saudável agora."""
        ts = now if now is not None else datetime.now(UTC)
        self.last_success[source_id] = ts
        self.consecutive_failures[source_id] = 0

    def record_failure(self, source_id: str, *, now: datetime | None = None) -> None:
        """Incrementa contagem de falhas consecutivas."""
        ts = now if now is not None else datetime.now(UTC)
        self.last_failure[source_id] = ts
        self.consecutive_failures[source_id] = self.consecutive_failures.get(source_id, 0) + 1

    def stale_sources(
        self, *, threshold: timedelta = timedelta(days=7), now: datetime | None = None
    ) -> list[str]:
        """Fontes sem sucesso há mais de `threshold`."""
        ts = now if now is not None else datetime.now(UTC)
        cutoff = ts - threshold
        return sorted(sid for sid, last_ok in self.last_success.items() if last_ok < cutoff)

    def chronically_failing(self, *, min_consecutive: int = 5) -> list[str]:
        """Fontes com N+ falhas consecutivas."""
        return sorted(
            sid for sid, count in self.consecutive_failures.items() if count >= min_consecutive
        )


# Singleton global, lazy-init
_heartbeat: SourceHeartbeat | None = None


def get_heartbeat() -> SourceHeartbeat:
    """Retorna singleton global."""
    global _heartbeat  # noqa: PLW0603 — singleton lazy-init intencional
    if _heartbeat is None:
        _heartbeat = SourceHeartbeat()
    return _heartbeat


def record_source_success(source_id: str) -> None:
    """Helper de conveniência."""
    get_heartbeat().record_success(source_id)


def record_source_failure(source_id: str) -> None:
    """Helper de conveniência."""
    get_heartbeat().record_failure(source_id)
