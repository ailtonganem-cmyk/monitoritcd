"""Audit log com hash chain.

Cada entry é imutável e referencia o hash da entry anterior.
Permite verificar integridade pós-fato (alguma entry foi modificada/removida?).

Princípios canônicos aplicados:
1. **Append-only**: a única operação é `append`. Storage NÃO expõe update/delete.
2. **Hash chain**: detectar tampering retroativo.
3. **owner_id assertion**: defense-in-depth.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from monitoritcd.core.models import AuditLogEntry

if TYPE_CHECKING:
    from monitoritcd.storage.base import StorageProtocol


class OwnershipError(Exception):
    """Operação rejeitada por owner_id incompatível."""


class AuditChainError(Exception):
    """Hash chain do audit log inconsistente — tampering detectado."""


def _hash_payload(payload: dict[str, Any]) -> str:
    """SHA-256 hex canônico de um payload (chaves ordenadas)."""
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLog:
    """Wrapper sobre `StorageProtocol` para append do audit log.

    Garante:
    - prev_hash correto (consultado antes de append)
    - payload_hash determinístico
    - entry_id único (uuid4)
    """

    def __init__(self, storage: StorageProtocol) -> None:
        self._storage = storage

    async def append(
        self,
        *,
        actor: str,
        action: str,
        payload: dict[str, Any],
        result: str = "success",
        error: str | None = None,
    ) -> AuditLogEntry:
        """Adiciona entry ao audit log com hash chain válida."""
        prev_hash = await self._storage.get_last_audit_hash()
        payload_hash = _hash_payload(payload)

        entry = AuditLogEntry(
            owner_id=self._storage.owner_id,
            entry_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            actor=actor,
            action=action,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
            result=result,  # type: ignore[arg-type]
            error=error,
        )
        await self._storage.append_audit(entry)
        return entry

    async def verify_chain(self, entries: list[AuditLogEntry]) -> None:
        """Valida que a chain é íntegra: cada entry referencia hash da anterior.

        Args:
            entries: lista de entries em ordem cronológica.

        Raises:
            AuditChainError: se chain está quebrada.
        """
        from monitoritcd.storage.in_memory import GENESIS_HASH  # noqa: PLC0415

        expected_prev = GENESIS_HASH
        for i, entry in enumerate(entries):
            if entry.prev_hash != expected_prev:
                msg = (
                    f"chain quebrada na posição {i}: "
                    f"esperado prev_hash={expected_prev!r}, recebido {entry.prev_hash!r}"
                )
                raise AuditChainError(msg)
            # Próximo prev_hash = hash desta entry
            entry_dict = entry.model_dump(mode="json")
            canonical = json.dumps(entry_dict, sort_keys=True, default=str)
            expected_prev = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
