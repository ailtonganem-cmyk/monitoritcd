"""Dead Letter Queue (Sugestão #31).

Itens que falharam N vezes em classify ou notify vão para DLQ.
Bot pode listar via `/dlq listar` (futuro). Hoje a fila é exposta via
método público no storage; em runtime, módulos que detectam N-ésima falha
chamam `enqueue`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

DLQReason = Literal[
    "classify_quota_exhausted",
    "classify_timeout",
    "notify_telegram_failed",
    "notify_email_failed",
    "storage_save_failed",
    "source_collect_failed_persistent",
]


@dataclass
class DLQEntry:
    """Entry da DLQ com contexto suficiente para reprocessamento manual."""

    entry_id: str
    timestamp: datetime
    reason: DLQReason
    attempt_count: int
    payload: dict  # type: ignore[type-arg]
    error_message: str

    @classmethod
    def create(
        cls,
        *,
        entry_id: str,
        reason: DLQReason,
        attempt_count: int,
        payload: dict,  # type: ignore[type-arg]
        error_message: str,
    ) -> DLQEntry:
        return cls(
            entry_id=entry_id,
            timestamp=datetime.now(UTC),
            reason=reason,
            attempt_count=attempt_count,
            payload=payload,
            error_message=error_message,
        )


class DeadLetterQueue:
    """In-memory DLQ. Para produção, plug-in num storage backend persistente."""

    def __init__(self) -> None:
        self._entries: list[DLQEntry] = []

    def enqueue(self, entry: DLQEntry) -> None:
        """Adiciona entry à fila."""
        self._entries.append(entry)

    def list_all(self) -> list[DLQEntry]:
        """Lista todas as entries."""
        return list(self._entries)

    def list_by_reason(self, reason: DLQReason) -> list[DLQEntry]:
        """Filtra por motivo."""
        return [e for e in self._entries if e.reason == reason]

    def remove(self, entry_id: str) -> bool:
        """Remove uma entry. Retorna True se encontrada."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.entry_id != entry_id]
        return len(self._entries) < before

    def __len__(self) -> int:
        return len(self._entries)
