"""CLI para verificar integridade do hash chain do audit log (#314 IDEAS.md).

Uso:
    python scripts/verify_audit_chain.py
    python scripts/verify_audit_chain.py --since 2026-01-01

Lê audit log do storage atual (Firestore ou InMemory) e valida que cada
entry tem `prev_hash` apontando para a entry imediatamente anterior.
Falha se detectar tampering.

Exit codes:
    0 — chain íntegra
    1 — tampering detectado
    2 — erro de leitura
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import AuditLogEntry


def _hash_payload(entry: AuditLogEntry) -> str:
    """Recalcula payload_hash a partir dos campos imutáveis."""
    canonical = (
        f"{entry.entry_id}|{entry.timestamp.isoformat()}|"
        f"{entry.actor}|{entry.action}|{entry.result}|{entry.error or ''}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_chain(
    entries: Sequence[AuditLogEntry],
    *,
    expected_genesis: str = "0" * 64,
) -> tuple[bool, list[str]]:
    """Verifica integridade do hash chain.

    Returns:
        (ok, errors). Lista de erros vazia se chain íntegra.
    """
    errors: list[str] = []
    prev_hash = expected_genesis
    for i, entry in enumerate(entries):
        # 1. prev_hash aponta para anterior?
        if entry.prev_hash != prev_hash:
            errors.append(
                f"entry #{i} ({entry.entry_id}): "
                f"prev_hash={entry.prev_hash[:8]}... esperado={prev_hash[:8]}..."
            )
        # 2. payload_hash bate com recálculo?
        recomputed = _hash_payload(entry)
        if recomputed != entry.payload_hash:
            errors.append(
                f"entry #{i} ({entry.entry_id}): payload_hash divergente "
                f"(armazenado={entry.payload_hash[:8]}, calculado={recomputed[:8]})"
            )
        # Próximo prev_hash = combinação dos dois (estratégia em audit_log.py).
        prev_hash = hashlib.sha256(
            (entry.payload_hash + entry.prev_hash).encode("utf-8")
        ).hexdigest()
    return len(errors) == 0, errors


async def main(args: argparse.Namespace) -> int:
    from monitoritcd.core.config import get_settings  # noqa: PLC0415
    from monitoritcd.storage.firestore_store import FirestoreStorage  # noqa: PLC0415

    settings = get_settings()
    storage = FirestoreStorage(
        project_id=settings.FIREBASE_PROJECT_ID,
        owner_id=settings.OWNER_ID,
    )
    try:
        # Limit alto para auditoria completa (cap a 10K para evitar runaway)
        entries = await storage.list_audit(limit=10000)
    except Exception as e:
        sys.stderr.write(f"Falha ao ler audit log: {e}\n")
        return 2

    if args.since:
        cutoff = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
        entries = [e for e in entries if e.timestamp >= cutoff]

    ok, errors = verify_chain(entries)
    if ok:
        print(f"✓ Audit chain íntegra ({len(entries)} entries verificadas)")
        return 0
    print(f"✗ Tampering detectado em {len(errors)} entries:")
    for err in errors[:20]:  # cap output
        print(f"  - {err}")
    return 1


def cli() -> int:
    parser = argparse.ArgumentParser(description="Verifica integridade do audit chain")
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Data ISO inicial (ex: 2026-01-01)",
    )
    args = parser.parse_args()
    return asyncio.run(main(args))


if __name__ == "__main__":
    sys.exit(cli())
