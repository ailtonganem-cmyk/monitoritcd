"""Backend Firestore real (produção).

Implementa `StorageProtocol` usando google-cloud-firestore async client.
Aplica `owner_id` assertion e queries scoped por owner em todas operações.

NOTA: testes unitários usam `InMemoryStorage`. Este backend é validado por
testes integration com Firebase emulator (Fase 9 do PLAN.md).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from monitoritcd.core.models import (
    ActiveStatesConfig,
    AuditLogEntry,
    Documento,
    NotificacaoStatus,
    StatusDocumento,
    Watch,
)
from monitoritcd.storage.audit_log import OwnershipError
from monitoritcd.storage.in_memory import GENESIS_HASH

if TYPE_CHECKING:
    from datetime import datetime

    from google.cloud.firestore import AsyncClient

    from monitoritcd.core.models import LLMResult

logger = structlog.get_logger(__name__)

# Coleções
COLLECTION_DOCUMENTOS = "documentos"
COLLECTION_ACTIVE_STATES = "config"
COLLECTION_WATCHES = "watches"
COLLECTION_AUDIT = "audit_log"


class FirestoreStorage:
    """Backend Firestore. Async via google-cloud-firestore."""

    def __init__(self, client: AsyncClient, owner_id: str) -> None:
        self._client = client
        self._owner_id = owner_id

    @property
    def owner_id(self) -> str:
        return self._owner_id

    def _assert_owner(self, doc_owner: str) -> None:
        if doc_owner != self._owner_id:
            msg = f"owner_id mismatch: expected {self._owner_id!r}, got {doc_owner!r}"
            raise OwnershipError(msg)

    # ─── Documentos ───────────────────────────────────────────────────────

    async def save_documento(self, doc: Documento) -> None:
        self._assert_owner(doc.owner_id)
        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc.doc_id)
        await ref.set(doc.model_dump(mode="json"))

    async def get_documento(self, doc_id: str) -> Documento | None:
        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc_id)
        snapshot = await ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data is None:  # pragma: no cover
            return None
        if data.get("owner_id") != self._owner_id:
            self._assert_owner(data.get("owner_id", ""))
        return Documento(**data)

    async def list_documentos(
        self,
        *,
        since: datetime | None = None,
        status: StatusDocumento | None = None,
        uf: str | None = None,
        limit: int = 100,
    ) -> list[Documento]:
        query: Any = self._client.collection(COLLECTION_DOCUMENTOS).where(
            "owner_id",
            "==",
            self._owner_id,
        )
        if status is not None:
            query = query.where("status", "==", status.value)
        if uf is not None:
            query = query.where("source.uf", "==", uf)
        if since is not None:
            query = query.where("original.fetched_at", ">=", since)
        query = query.order_by("original.fetched_at", direction="DESCENDING").limit(limit)

        results: list[Documento] = []
        async for snapshot in query.stream():
            data = snapshot.to_dict()
            if data and data.get("owner_id") == self._owner_id:
                results.append(Documento(**data))
        return results

    async def update_llm(self, doc_id: str, llm: LLMResult) -> None:
        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc_id)
        # Read-validate-write para garantir owner check
        snapshot = await ref.get()
        if not snapshot.exists:
            msg = f"Documento não encontrado: {doc_id}"
            raise ValueError(msg)
        data = snapshot.to_dict() or {}
        self._assert_owner(data.get("owner_id", ""))
        await ref.update({"llm": llm.model_dump(mode="json")})

    async def update_notificacao(
        self,
        doc_id: str,
        notificacao: NotificacaoStatus,
    ) -> None:
        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc_id)
        snapshot = await ref.get()
        if not snapshot.exists:
            msg = f"Documento não encontrado: {doc_id}"
            raise ValueError(msg)
        data = snapshot.to_dict() or {}
        self._assert_owner(data.get("owner_id", ""))
        await ref.update({"notificacao": notificacao.model_dump(mode="json")})

    async def update_status(self, doc_id: str, status: StatusDocumento) -> None:
        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc_id)
        snapshot = await ref.get()
        if not snapshot.exists:
            msg = f"Documento não encontrado: {doc_id}"
            raise ValueError(msg)
        data = snapshot.to_dict() or {}
        self._assert_owner(data.get("owner_id", ""))
        await ref.update({"status": status.value})

    async def exists_by_hash(self, content_hash: str) -> bool:
        query = (
            self._client.collection(COLLECTION_DOCUMENTOS)
            .where("owner_id", "==", self._owner_id)
            .where("original.content_hash", "==", content_hash)
            .limit(1)
        )
        async for _ in query.stream():
            return True
        return False

    # ─── Active states ────────────────────────────────────────────────────

    async def get_active_states(self) -> ActiveStatesConfig | None:
        ref = self._client.collection(COLLECTION_ACTIVE_STATES).document("active_states")
        snapshot = await ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data is None:  # pragma: no cover
            return None
        if data.get("owner_id") != self._owner_id:
            self._assert_owner(data.get("owner_id", ""))
        return ActiveStatesConfig(**data)

    async def save_active_states(self, config: ActiveStatesConfig) -> None:
        self._assert_owner(config.owner_id)
        ref = self._client.collection(COLLECTION_ACTIVE_STATES).document("active_states")
        await ref.set(config.model_dump(mode="json"))

    # ─── Watch list ───────────────────────────────────────────────────────

    async def save_watch(self, watch: Watch) -> None:
        self._assert_owner(watch.owner_id)
        ref = self._client.collection(COLLECTION_WATCHES).document(watch.watch_id)
        await ref.set(watch.model_dump(mode="json"))

    async def list_watches(self) -> list[Watch]:
        query = self._client.collection(COLLECTION_WATCHES).where(
            "owner_id",
            "==",
            self._owner_id,
        )
        results: list[Watch] = []
        async for snapshot in query.stream():
            data = snapshot.to_dict()
            if data and data.get("owner_id") == self._owner_id:
                results.append(Watch(**data))
        return results

    async def delete_watch(self, watch_id: str) -> None:
        ref = self._client.collection(COLLECTION_WATCHES).document(watch_id)
        snapshot = await ref.get()
        if snapshot.exists:
            data = snapshot.to_dict() or {}
            self._assert_owner(data.get("owner_id", ""))
            await ref.delete()

    # ─── Audit log ────────────────────────────────────────────────────────

    async def append_audit(self, entry: AuditLogEntry) -> None:
        self._assert_owner(entry.owner_id)
        ref = self._client.collection(COLLECTION_AUDIT).document(entry.entry_id)
        await ref.set(entry.model_dump(mode="json"))

    async def get_last_audit_hash(self) -> str:
        query = (
            self._client.collection(COLLECTION_AUDIT)
            .where("owner_id", "==", self._owner_id)
            .order_by("timestamp", direction="DESCENDING")
            .limit(1)
        )
        async for snapshot in query.stream():
            data = snapshot.to_dict() or {}
            # Hash desta entry vira prev_hash da próxima
            import hashlib  # noqa: PLC0415
            import json  # noqa: PLC0415

            canonical = json.dumps(data, sort_keys=True, default=str)
            return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return GENESIS_HASH
