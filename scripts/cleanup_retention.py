#!/usr/bin/env python3
"""Aplica retenção configurada.

Política (definida em CLAUDE.md Seção 4):
- Descartados pelo LLM (relevancia < 5): purgar após 90 dias.
- audit_log: manter 1 ano.
- execucoes/: manter 6 meses.
- Documentos com relevância >= 5: indefinido (mantém).

Uso:
    python scripts/cleanup_retention.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

DESCARTADO_RETENTION_DAYS = 90
AUDIT_RETENTION_DAYS = 365
EXECUCOES_RETENTION_DAYS = 180


def cleanup(*, dry_run: bool) -> int:
    """Executa cleanup. Retorna count purgado."""
    try:
        from google.cloud.firestore import Client  # noqa: PLC0415
    except ImportError:
        print("google-cloud-firestore não disponível", file=sys.stderr)
        return 0

    client = Client()
    now = datetime.now(UTC)
    cutoff_descartado = now - timedelta(days=DESCARTADO_RETENTION_DAYS)
    cutoff_audit = now - timedelta(days=AUDIT_RETENTION_DAYS)
    cutoff_exec = now - timedelta(days=EXECUCOES_RETENTION_DAYS)

    purged = 0

    # Documentos descartados
    print(f"Purgando documentos descartados < {cutoff_descartado.isoformat()}...")
    query = (
        client.collection("documentos")
        .where("llm.severity_tier", "==", "descartado")
        .where("original.fetched_at", "<", cutoff_descartado)
        .limit(500)
    )
    for snap in query.stream():
        purged += 1
        if dry_run:
            print(f"  [DRY] documentos/{snap.id}")
        else:
            snap.reference.delete()

    # Audit log antigo
    print(f"Purgando audit_log < {cutoff_audit.isoformat()}...")
    query2 = client.collection("audit_log").where("timestamp", "<", cutoff_audit).limit(500)
    for snap in query2.stream():
        purged += 1
        if dry_run:
            print(f"  [DRY] audit_log/{snap.id}")
        else:
            snap.reference.delete()

    # Execuções antigas (se collection existir)
    print(f"Purgando execucoes < {cutoff_exec.isoformat()}...")
    query3 = client.collection("execucoes").where("started_at", "<", cutoff_exec).limit(500)
    for snap in query3.stream():
        purged += 1
        if dry_run:
            print(f"  [DRY] execucoes/{snap.id}")
        else:
            snap.reference.delete()

    return purged


def main() -> int:
    parser = argparse.ArgumentParser(description="Aplica política de retenção")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    purged = cleanup(dry_run=args.dry_run)
    print(f"Total purgado: {purged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
