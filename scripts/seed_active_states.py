#!/usr/bin/env python3
"""Seed/atualiza config de UFs ativas no Firestore.

Operacional: criar config inicial ou ativar UFs em massa antes de ter o
bot Telegram funcional. Depois de rodado, mudanças individuais devem ir
pelo bot (`/estados ativar UF`).

Uso:
    python scripts/seed_active_states.py --ufs SP RJ MG RS DF
    python scripts/seed_active_states.py --ufs SP --federal-active false

Exige `GOOGLE_APPLICATION_CREDENTIALS` apontando para service account JSON
do projeto Firebase, e `OWNER_ID` no env.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime


async def main(ufs: list[str], *, federal_active: bool, dry_run: bool) -> int:
    from google.cloud.firestore import AsyncClient  # noqa: PLC0415

    from monitoritcd.core.models import ActiveStatesConfig  # noqa: PLC0415
    from monitoritcd.storage.firestore_store import FirestoreStorage  # noqa: PLC0415

    owner_id = os.environ.get("OWNER_ID")
    if not owner_id:
        print("ERRO: OWNER_ID não definido em env", file=sys.stderr)
        return 1

    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    if not project_id:
        print("ERRO: FIREBASE_PROJECT_ID não definido em env", file=sys.stderr)
        return 1

    client = AsyncClient(project=project_id)
    storage = FirestoreStorage(client, owner_id)

    current = await storage.get_active_states()
    print(
        f"Atual: active_uf={current.active_uf if current else []}, "
        f"federal_active={current.federal_active if current else True}"
    )

    new_config = ActiveStatesConfig(
        owner_id=owner_id,
        active_uf=sorted(set(ufs)),
        federal_active=federal_active,
        silenced_until={},
        updated_at=datetime.now(UTC),
        updated_by="seed_active_states",
    )
    print(f"Novo:  active_uf={new_config.active_uf}, federal_active={new_config.federal_active}")

    if dry_run:
        print("[dry-run] Nada salvo.")
        return 0

    await storage.save_active_states(new_config)
    print("✅ Config salva no Firestore.")
    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ufs",
        nargs="+",
        default=["SP", "RJ", "MG", "RS", "DF"],
        help="Lista de UFs a ativar (default: MVP enxuto)",
    )
    parser.add_argument(
        "--federal-active",
        type=lambda x: x.lower() != "false",
        default=True,
        help="Habilitar fontes federais (default: true)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra a config sem salvar",
    )
    args = parser.parse_args()

    return asyncio.run(main(args.ufs, federal_active=args.federal_active, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(cli())
