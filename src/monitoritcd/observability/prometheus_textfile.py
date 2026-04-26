"""Métricas Prometheus em formato textfile (Sugestão #27).

Escreve métricas no formato `node_exporter --collector.textfile.directory`,
permitindo que qualquer Prometheus rode `node_exporter` para colher dados.

Formato textfile:
    # HELP nome_metrica descrição
    # TYPE nome_metrica counter|gauge|histogram
    nome_metrica{label="valor"} 42
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def _format_labels(labels: dict[str, str] | None) -> str:
    """Formata labels para o protocolo textfile."""
    if not labels:
        return ""
    parts = ",".join(f'{k}="{_escape(v)}"' for k, v in sorted(labels.items()))
    return "{" + parts + "}"


def _escape(value: str) -> str:
    r"""Escape para o formato textfile (\\, \n, \" são especiais)."""
    return value.replace("\\", r"\\").replace('"', r"\"").replace("\n", r"\n")


def write_metrics(
    path: Path,
    metrics: dict[str, dict[str, Any]],
) -> None:
    """Escreve métricas no `path`.

    Args:
        path: arquivo de saída (ex: /tmp/monitoritcd.prom).
        metrics: dict de métricas no formato:
            {
              "metric_name": {
                "type": "counter" | "gauge",
                "help": "descrição",
                "value": float,
                "labels": {"key": "value"} | None,
              }
            }
    """
    lines: list[str] = []
    for name, spec in metrics.items():
        help_text = spec.get("help", "")
        mtype = spec.get("type", "gauge")
        value = spec.get("value", 0)
        labels = spec.get("labels")

        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")
        labels_str = _format_labels(labels)
        lines.append(f"{name}{labels_str} {value}")

    # Escreve atomicamente (escrever em .tmp, depois rename) para evitar
    # leituras parciais pelo node_exporter.
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def emit_run_metrics(
    path: Path,
    *,
    items_collected: int,
    items_classified: int,
    items_stored: int,
    sources_consulted: int,
    sources_failed: int,
    duration_seconds: float,
) -> None:
    """Emite métricas padronizadas de uma execução do pipeline."""
    metrics = {
        "monitoritcd_items_collected": {
            "type": "counter",
            "help": "Itens coletados de fontes",
            "value": items_collected,
        },
        "monitoritcd_items_classified": {
            "type": "counter",
            "help": "Itens classificados pelo LLM",
            "value": items_classified,
        },
        "monitoritcd_items_stored": {
            "type": "counter",
            "help": "Itens persistidos no Firestore",
            "value": items_stored,
        },
        "monitoritcd_sources_consulted": {
            "type": "gauge",
            "help": "Fontes consultadas nesta execução",
            "value": sources_consulted,
        },
        "monitoritcd_sources_failed": {
            "type": "gauge",
            "help": "Fontes que falharam nesta execução",
            "value": sources_failed,
        },
        "monitoritcd_run_duration_seconds": {
            "type": "gauge",
            "help": "Duração da execução em segundos",
            "value": duration_seconds,
        },
    }
    write_metrics(path, metrics)
