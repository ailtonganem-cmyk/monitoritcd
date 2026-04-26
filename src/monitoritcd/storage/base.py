"""Protocol da camada de storage.

Define a interface mínima que qualquer backend (Firestore, in-memory, SQLite)
deve implementar. Permite swap de backend sem tocar no resto do código.

Princípios canônicos aplicados:
1. **`assert_owner` obrigatório** em toda mutation — defense-in-depth contra
   blast radius (mesmo single-user).
2. **Errors específicas** (`OwnershipError`, `DocumentNotFoundError`) — chamador
   pode decidir comportamento sem inspecionar exception strings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from monitoritcd.core.models import (
        ActiveStatesConfig,
        AuditLogEntry,
        Documento,
        LLMResult,
        NotificacaoStatus,
        StatusDocumento,
        Watch,
    )


class StorageProtocol(Protocol):
    """Interface mínima de storage."""

    @property
    def owner_id(self) -> str:
        """ID do dono — todo doc deve bater com este."""
        ...

    # ─── Documentos ───────────────────────────────────────────────────────
    async def save_documento(self, doc: Documento) -> None: ...

    async def get_documento(self, doc_id: str) -> Documento | None: ...

    async def list_documentos(
        self,
        *,
        since: datetime | None = None,
        status: StatusDocumento | None = None,
        uf: str | None = None,
        limit: int = 100,
    ) -> list[Documento]: ...

    async def update_llm(self, doc_id: str, llm: LLMResult) -> None: ...

    async def update_notificacao(
        self,
        doc_id: str,
        notificacao: NotificacaoStatus,
    ) -> None: ...

    async def update_status(self, doc_id: str, status: StatusDocumento) -> None: ...

    async def add_user_tag(self, doc_id: str, tag: str) -> None:
        """Adiciona tag pessoal do dono ao documento (idempotente).

        Diferente de `llm.tags` (write-once via update_llm), `user_tags`
        cresce ao longo do tempo conforme o dono marca documentos via
        `/marcar` no bot. Idempotente: re-adicionar mesma tag não duplica.
        """
        ...

    async def remove_user_tag(self, doc_id: str, tag: str) -> None:
        """V6 (Pentest): remove tag pessoal do dono. Idempotente.

        Operação atômica que preserva `original` write-once. Não levanta
        erro se a tag não existir (idempotência).
        """
        ...

    async def exists_by_hash(self, content_hash: str) -> bool:
        """True se há doc com este content_hash do dono."""
        ...

    # ─── Active states ────────────────────────────────────────────────────
    async def get_active_states(self) -> ActiveStatesConfig | None: ...

    async def save_active_states(self, config: ActiveStatesConfig) -> None: ...

    # ─── Watch list ───────────────────────────────────────────────────────
    async def save_watch(self, watch: Watch) -> None: ...

    async def list_watches(self) -> list[Watch]: ...

    async def delete_watch(self, watch_id: str) -> None: ...

    # ─── Audit log ────────────────────────────────────────────────────────
    async def append_audit(self, entry: AuditLogEntry) -> None: ...

    async def get_last_audit_hash(self) -> str: ...
