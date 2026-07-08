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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

# V3 (Pentest 2026-04-26 / Alta) — restore.py hardening:
# 1. Verificação SHA-256 do .age (gerada por backup.py:109)
# 2. Validação de owner_id contra OWNER_ID env var
# 3. Allowlist de coleções restauráveis
# 4. Validação de doc_id (sem path traversal nem chars perigosos)

ALLOWED_COLLECTIONS: Final[frozenset[str]] = frozenset(
    {
        "monitor_documentos",
        "monitor_watches",
        "monitor_audit_log",
        "monitor_config",
        "monitor_runs",
    }
)
DOC_ID_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_:.\-]{1,128}$")


class RestoreIntegrityError(Exception):
    """Erro de integridade durante restore (SHA mismatch, owner errado, etc.)."""


def verify_sha256(backup_path: Path, expected: str) -> None:
    """V3: verifica SHA-256 do .age contra valor esperado."""
    h = hashlib.sha256()
    with backup_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if not _constant_time_eq(actual, expected):
        msg = (
            f"SHA-256 mismatch — backup adulterado ou corrompido.\n"
            f"  esperado: {expected}\n"
            f"  obtido:   {actual}"
        )
        raise RestoreIntegrityError(msg)


def _constant_time_eq(a: str, b: str) -> bool:
    """Comparação constant-time para evitar timing oracle."""
    import secrets  # noqa: PLC0415

    return secrets.compare_digest(a, b)


def _resolve_age_binary() -> str:
    """V11: resolve `age` por path absoluto (defesa contra PATH hijacking)."""
    path = shutil.which("age")
    if path is None:
        msg = "Binário `age` não encontrado em PATH."
        raise RestoreIntegrityError(msg)
    return path


def decrypt_with_age(encrypted: bytes, identity_path: Path) -> bytes:
    """Decifra usando `age` com chave privada em `identity_path`."""
    age_bin = _resolve_age_binary()
    proc = subprocess.run(
        [age_bin, "--decrypt", "--identity", str(identity_path), "--output", "-"],
        input=encrypted,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def _validate_payload(payload: dict[str, Any], expected_owner: str) -> None:
    """V3: valida owner_id, version e shape básico antes de restaurar."""
    if payload.get("version") != 1:
        msg = f"Versão {payload.get('version')} não suportada (esperado: 1)"
        raise RestoreIntegrityError(msg)

    payload_owner = payload.get("owner_id")
    if not payload_owner:
        msg = "Backup sem owner_id — recusa segura."
        raise RestoreIntegrityError(msg)
    if not _constant_time_eq(payload_owner, expected_owner):
        msg = (
            f"owner_id mismatch — backup pertence a outro tenant.\n"
            f"  esperado: {expected_owner}\n"
            f"  no backup: {payload_owner}"
        )
        raise RestoreIntegrityError(msg)

    if not isinstance(payload.get("collections"), dict):
        msg = "Payload sem 'collections' dict válido."
        raise RestoreIntegrityError(msg)


def restore_firestore(payload: dict[str, Any], *, dry_run: bool) -> int:
    """Restaura documentos no Firestore. Retorna nº de docs restaurados.

    V3: aplica allowlist de coleções e regex em doc_ids.
    """
    try:
        from google.cloud.firestore import Client  # noqa: PLC0415
    except ImportError:
        print("google-cloud-firestore não disponível", file=sys.stderr)
        return 0

    client = None if dry_run else Client()

    count = 0
    skipped: list[str] = []
    for col_name, docs in payload["collections"].items():
        if col_name not in ALLOWED_COLLECTIONS:
            skipped.append(f"coleção rejeitada: {col_name!r}")
            continue
        for doc in docs:
            doc_id = doc.pop("_doc_id", None)
            if doc_id is None:
                continue
            if not isinstance(doc_id, str) or not DOC_ID_REGEX.match(doc_id):
                skipped.append(f"doc_id rejeitado: {col_name}/{doc_id!r}")
                continue
            count += 1
            if dry_run:
                print(f"  [DRY] {col_name}/{doc_id}")
            else:
                client.collection(col_name).document(doc_id).set(doc)  # type: ignore[union-attr]

    if skipped:
        print(f"⚠️  {len(skipped)} entradas rejeitadas por validação:", file=sys.stderr)
        for s in skipped[:10]:
            print(f"  - {s}", file=sys.stderr)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura backup cifrado")
    parser.add_argument("backup", help="Path do .age cifrado")
    parser.add_argument("--identity", required=True, help="Chave privada age (arquivo)")
    parser.add_argument(
        "--expected-sha256",
        required=True,
        help="SHA-256 esperado do .age (gerado por backup.py)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Pula confirmação interativa")
    args = parser.parse_args()

    expected_owner = os.environ.get("OWNER_ID")
    if not expected_owner:
        print("ERRO: OWNER_ID não definido em env", file=sys.stderr)
        return 1

    backup_path = Path(args.backup)
    identity_path = Path(args.identity)
    if not backup_path.is_file():
        print(f"ERRO: backup não encontrado: {backup_path}", file=sys.stderr)
        return 1
    if not identity_path.is_file():
        print(f"ERRO: identity não encontrado: {identity_path}", file=sys.stderr)
        return 1

    try:
        print(f"Verificando integridade SHA-256 de {backup_path}...")
        verify_sha256(backup_path, args.expected_sha256)
        print("  ✓ SHA-256 OK")

        print("Decifrando...")
        encrypted = backup_path.read_bytes()
        decrypted = decrypt_with_age(encrypted, identity_path)
        raw = gzip.decompress(decrypted)
        payload = json.loads(raw.decode("utf-8"))

        print("Validando payload...")
        _validate_payload(payload, expected_owner)
        print("  ✓ owner_id e versão OK")
    except RestoreIntegrityError as e:
        print(f"ERRO DE INTEGRIDADE: {e}", file=sys.stderr)
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
