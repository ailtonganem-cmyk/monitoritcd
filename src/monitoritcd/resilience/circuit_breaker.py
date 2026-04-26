"""Circuit breaker per-source (Sugestão #45).

Após N falhas consecutivas, fonte é automaticamente silenciada por X horas.
Próxima execução tenta e re-engata se voltar.

Estados:
- CLOSED: requests passam normalmente.
- OPEN: requests bloqueadas (fail fast).
- HALF_OPEN: 1 request de teste após cooldown; sucesso volta a CLOSED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class CircuitState(StrEnum):
    """Estado do circuit."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Levantada quando circuit está OPEN — fail fast."""


@dataclass
class _CircuitData:
    """Estado interno por chave."""

    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    opened_at: datetime | None = None


@dataclass
class CircuitBreaker:
    """Circuit breaker simples por chave (source_id).

    Args:
        failure_threshold: N falhas consecutivas → abre.
        cooldown: tempo em OPEN antes de tentar HALF_OPEN.
    """

    failure_threshold: int = 5
    cooldown: timedelta = timedelta(hours=1)
    _circuits: dict[str, _CircuitData] = field(default_factory=dict)

    def _data(self, key: str) -> _CircuitData:
        return self._circuits.setdefault(key, _CircuitData())

    def state(self, key: str, *, now: datetime | None = None) -> CircuitState:
        """Retorna estado, transitando OPEN→HALF_OPEN se cooldown passou."""
        ts = now if now is not None else datetime.now(UTC)
        c = self._data(key)
        if (
            c.state == CircuitState.OPEN
            and c.opened_at is not None
            and ts - c.opened_at >= self.cooldown
        ):
            c.state = CircuitState.HALF_OPEN
        return c.state

    def check(self, key: str, *, now: datetime | None = None) -> None:
        """Levanta `CircuitBreakerError` se OPEN."""
        if self.state(key, now=now) == CircuitState.OPEN:
            msg = f"circuit aberto para {key!r}"
            raise CircuitBreakerError(msg)

    def record_success(self, key: str) -> None:
        """Sucesso: reseta failures e volta a CLOSED."""
        c = self._data(key)
        c.state = CircuitState.CLOSED
        c.failures = 0
        c.opened_at = None

    def record_failure(self, key: str, *, now: datetime | None = None) -> None:
        """Falha: incrementa contador; abre ao atingir threshold."""
        ts = now if now is not None else datetime.now(UTC)
        c = self._data(key)
        c.failures += 1
        if c.failures >= self.failure_threshold:
            c.state = CircuitState.OPEN
            c.opened_at = ts

    def reset(self, key: str) -> None:
        """Reset manual (operação destrutiva — útil em testes)."""
        self._circuits.pop(key, None)
