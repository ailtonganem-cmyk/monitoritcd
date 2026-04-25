#!/usr/bin/env python3
"""Restaura backup cifrado para Firestore.

⚠️ OPERAÇÃO DESTRUTIVA. Requer confirmação interativa.

Uso:
    AGE_SECRET_KEY=AGE-SECRET-KEY-... python scripts/restore.py backup.age

Etapas:
1. Decifra com `age` usando chave privada (AGE_SECRET_KEY).
2. Descomprime gzip.
3. Valida JSON contra schema (versão).
4. Pede confirmação interativa.
5. Restaura em Firestore (upsert por doc_id).

Não toca em backups existentes; apenas escreve.
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def decrypt_with_age(encrypted: bytes, identity_path: Path) -> bytes:
    """Decifra usando `age` com chave privada em `identity_path`."""
    proc = subprocess.run(
        ["age", "--decrypt", "--identity", str(identity_path), "--output", "-"],
        input=encrypted,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def restore_firestore(payload: dict[str, Any], *, dry_run: bool) -> int:
    """Restaura documentos no Firestore. Retorna nº de docs restaurados."""
    try:
        from google.cloud.firestore import Client  # noqa: PLC0415
    except ImportError:
        print("google-cloud-firestore não disponível", file=sys.stderr)
        return 0

    client = None if dry_run else Client()

    count = 0
    for col_name, docs in payload["collections"].items():
        for doc in docs:
            doc_id = doc.pop("_doc_id", None)
            if doc_id is None:
                continue
            count += 1
            if dry_run:
                print(f"  [DRY] {col_name}/{doc_id}")
            else:
                client.collection(col_name).document(doc_id).set(doc)  # type: ignore[union-attr]
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura backup cifrado")
    parser.add_argument("backup", help="Path do .age cifrado")
    parser.add_argument("--identity", required=True, help="Chave privada age (arquivo)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Pula confirmação interativa")
    args = parser.parse_args()

    backup_path = Path(args.backup)
    identity_path = Path(args.identity)
    if not backup_path.is_file():
        print(f"ERRO: backup não encontrado: {backup_path}", file=sys.stderr)
        return 1
    if not identity_path.is_file():
        print(f"ERRO: identity não encontrado: {identity_path}", file=sys.stderr)
        return 1

    print(f"Decifrando {backup_path}...")
    encrypted = backup_path.read_bytes()
    decrypted = decrypt_with_age(encrypted, identity_path)
    raw = gzip.decompress(decrypted)
    payload = json.loads(raw.decode("utf-8"))

    if payload.get("version") != 1:
        print(f"ERRO: versão {payload.get('version')} não suportada", file=sys.stderr)
        return 1

    total = sum(len(v) for v in payload["collections"].values())
    print(f"  Backup com {total} documentos de {payload.get('exported_at')}")
    print(f"  Owner: {payload.get('owner_id')}")

    if not args.yes and not args.dry_run:
        confirm = input("Restaurar para Firestore? [sim/NÃO]: ")
        if confirm.lower() not in {"sim", "yes", "y"}:
            print("Cancelado.")
            return 0

    restored = restore_firestore(payload, dry_run=args.dry_run)
    print(f"Restaurados: {restored} documentos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
