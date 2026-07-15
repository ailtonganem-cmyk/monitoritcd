#!/usr/bin/env python3
"""Reconcilia `owner_id` de documentos poluídos por run local incorreto.

Contexto (incidente 2026-07-09, ver `orchestrator.py`): um run LOCAL com
`.env` apontando para o projeto de produção `sefworkstation-app` gravou ~14
docs em `monitor_documentos` com `owner_id="sefworkstation-monitor-homolog"`
(valor de homolog) em vez do canônico `ailton-ganem-monitor`. O guard
write-once `_assert_owner` (`monitoritcd.storage.firestore_store`) colide
nesses docs a cada run subsequente do cron.

Uso — dry-run (default, zero escrita):
    python scripts/reconcile_owner.py --project=sefworkstation-app \\
        --owner-atual=sefworkstation-monitor-homolog \\
        --owner-canonico=ailton-ganem-monitor

Uso — aplica a correção:
    python scripts/reconcile_owner.py --project=sefworkstation-app \\
        --owner-atual=sefworkstation-monitor-homolog \\
        --owner-canonico=ailton-ganem-monitor --apply

Reatribui SÓ o campo `owner_id` (update parcial) — nunca sobrescreve o doc
inteiro, nunca deleta. Idempotente: reexecutar após `--apply` encontra 0 docs.
"""

from __future__ import annotations

import argparse
import sys
from typing import Final

COLLECTION_DOCUMENTOS: Final[str] = "monitor_documentos"
ALLOWED_PROJECTS: Final[frozenset[str]] = frozenset({"sefworkstation-app", "sefworkstation-hml"})


def assert_safe_project(project: str) -> None:
    """Recusa qualquer projeto fora da allowlist — nunca escrever no projeto errado."""
    if project not in ALLOWED_PROJECTS:
        msg = f"projeto {project!r} não permitido (esperado um de: {sorted(ALLOWED_PROJECTS)})"
        raise ValueError(msg)


def reconcile(*, project: str, owner_atual: str, owner_canonico: str, apply: bool) -> int:
    """Reconcilia `owner_id`. Retorna a contagem de docs encontrados/atualizados."""
    try:
        from google.cloud.firestore import Client  # noqa: PLC0415
    except ImportError:
        print("google-cloud-firestore não disponível", file=sys.stderr)
        return 0

    client = Client(project=project)
    query = client.collection(COLLECTION_DOCUMENTOS).where("owner_id", "==", owner_atual)

    count = 0
    for snap in query.stream():
        count += 1
        if apply:
            snap.reference.update({"owner_id": owner_canonico})
            print(f"  [APPLY] {COLLECTION_DOCUMENTOS}/{snap.id}")
        else:
            print(f"  [DRY] {COLLECTION_DOCUMENTOS}/{snap.id}")

    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--project", required=True, help="ID do projeto Firebase")
    parser.add_argument("--owner-atual", required=True, help="owner_id poluído a corrigir")
    parser.add_argument("--owner-canonico", required=True, help="owner_id canônico do pipeline")
    parser.add_argument("--apply", action="store_true", help="Aplica a correção (default: dry-run)")
    args = parser.parse_args()

    try:
        assert_safe_project(args.project)
    except ValueError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    if args.owner_atual == args.owner_canonico:
        print(
            "ERRO: --owner-atual e --owner-canonico são iguais — nada a reconciliar",
            file=sys.stderr,
        )
        return 1

    modo = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{modo}] projeto={args.project} "
        f"owner_atual={args.owner_atual!r} -> owner_canonico={args.owner_canonico!r}"
    )

    count = reconcile(
        project=args.project,
        owner_atual=args.owner_atual,
        owner_canonico=args.owner_canonico,
        apply=args.apply,
    )
    acao = "reconciliado(s)" if args.apply else "encontrado(s)"
    print(f"Total: {count} documento(s) {acao}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
