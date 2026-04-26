"""Subsistema de observabilidade (Sugestões #27-#32).

Componentes:
- `prometheus_textfile`: escreve métricas em formato Prometheus textfile.
- `tracing`: integração opcional com OpenTelemetry.
- `dlq`: dead-letter queue para itens com falhas persistentes.
- `source_heartbeat`: tracking per-source de última coleta bem-sucedida.

Princípio aplicado: tudo no-op por default. Habilitação via env var explícita.
"""

from monitoritcd.observability.dlq import DeadLetterQueue, DLQEntry
from monitoritcd.observability.prometheus_textfile import write_metrics
from monitoritcd.observability.source_heartbeat import (
    SourceHeartbeat,
    record_source_failure,
    record_source_success,
)

__all__ = [
    "DLQEntry",
    "DeadLetterQueue",
    "SourceHeartbeat",
    "record_source_failure",
    "record_source_success",
    "write_metrics",
]
