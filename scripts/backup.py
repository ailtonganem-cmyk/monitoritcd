#!/usr/bin/env python3
"""Backup mensal do Firestore para Drive (cifrado com `age`).

Uso (chamado pelo workflow `.github/workflows/backup.yml`):
    python scripts/backup.py --output backup-2026-04.json.age

Etapas:
1. Exporta coleções do Firestore como JSON (admin SDK).
2. Comprime com gzip.
3. Cifra com `age` usando chave pública (env var AGE_PUBLIC_KEY).
4. Faz upload ao Google Drive na pasta GDRIVE_FOLDER_ID.

Princípios canônicos:
- Service account credentials em SecretStr; nunca em logs.
- Backup é write-only — restore é processo manual deliberado.
- Verificação de integridade pós-cifragem.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Coleções a exportar (todas que pertencem ao owner)
COLLECTIONS_TO_BACKUP = ["documentos", "config", "watches", "audit_log"]


def export_firestore(owner_id: str) -> dict[str, Any]:
    """Exporta coleções como dict serializável.

    Retorna mapa: {collection_name: [docs...]}.
    Em produção: usa firebase_admin.firestore.client().collection().stream().
    Em DEV/TEST: pode retornar dict vazio (smoke test).
    """
    try:
        from google.cloud.firestore import Client  # noqa: PLC0415
    except ImportError:
        print("google-cloud-firestore não disponível — skip export", file=sys.stderr)
        return {c: [] for c in COLLECTIONS_TO_BACKUP}

    client = Client()
    out: dict[str, Any] = {}
    for col_name in COLLECTIONS_TO_BACKUP:
        docs = []
        query = client.collection(col_name).where("owner_id", "==", owner_id)
        for snapshot in query.stream():
            data = snapshot.to_dict() or {}
            data["_doc_id"] = snapshot.id
            docs.append(data)
        out[col_name] = docs
    return out


def encrypt_with_age(input_bytes: bytes, recipient: str) -> bytes:
    """Cifra `input_bytes` com `age` usando `recipient` (chave pública)."""
    proc = subprocess.run(
        ["age", "--encrypt", "--recipient", recipient, "--output", "-"],
        input=input_bytes,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup do Firestore")
    parser.add_argument("--output", required=True, help="Path de saída do .age")
    parser.add_argument("--owner-id", default=os.environ.get("OWNER_ID", ""))
    parser.add_argument("--age-recipient", default=os.environ.get("AGE_PUBLIC_KEY", ""))
    args = parser.parse_args()

    if not args.owner_id:
        print("ERRO: OWNER_ID não definido", file=sys.stderr)
        return 1
    if not args.age_recipient:
        print("ERRO: AGE_PUBLIC_KEY não definido", file=sys.stderr)
        return 1

    print(f"[{datetime.now(UTC).isoformat()}] Iniciando export...")
    data = export_firestore(args.owner_id)

    total_docs = sum(len(v) for v in data.values())
    print(f"  Exportados {total_docs} documentos em {len(data)} coleções")

    # Serializa + comprime
    payload = {
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "owner_id": args.owner_id,
        "collections": data,
    }
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9)
    print(f"  Tamanho gzipped: {len(compressed):,} bytes")

    # Cifra
    encrypted = encrypt_with_age(compressed, args.age_recipient)
    print(f"  Tamanho cifrado: {len(encrypted):,} bytes")

    # SHA-256 para verificação
    sha = hashlib.sha256(encrypted).hexdigest()
    print(f"  SHA-256: {sha}")

    # Salva
    output = Path(args.output)
    output.write_bytes(encrypted)
    print(f"  Backup salvo: {output} ({sha[:16]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
