"""Storage in-memory para testes e dev.

Implementa `StorageProtocol` em RAM (sem persistência). Usado em todos os
testes para evitar dependência do Firebase emulator.

Aplica todas as garantias do protocol:
- `assert_owner` em mutations
- Hash chain do audit log
- Imutabilidade de audit entries
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING

from monitoritcd.storage.audit_log import OwnershipError

if TYPE_CHECKING:
    from datetime import datetime

    from monitoritcd.core.models import (
        ActiveStatesConfig,
        AuditLogEntry,
        Documento,
        ExtraKeywordsConfig,
        ExtraTopicsConfig,
        LLMResult,
        NotificacaoStatus,
        StatusDocumento,
        Watch,
    )


class DocumentNotFoundError(Exception):
    """Documento não encontrado no storage."""


GENESIS_HASH = "0" * 64  # hash do "antes do primeiro entry" (audit chain start)


class InMemoryStorage:
    """Backend in-memory."""

    def __init__(self, owner_id: str) -> None:
        self._owner_id = owner_id
        self._documentos: dict[str, Documento] = {}
        self._active_states: ActiveStatesConfig | None = None
        self._extra_keywords: ExtraKeywordsConfig | None = None
        self._extra_topics: ExtraTopicsConfig | None = None
        self._watches: dict[str, Watch] = {}
        self._audit: list[AuditLogEntry] = []

    @property
    def owner_id(self) -> str:
        return self._owner_id

    def _assert_owner(self, doc_owner: str) -> None:
        if doc_owner != self._owner_id:
            msg = f"owner_id mismatch: expected {self._owner_id!r}, got {doc_owner!r}"
            raise OwnershipError(msg)

    # ─── Documentos ───────────────────────────────────────────────────────

    async def save_documento(self, doc: Documento) -> None:
        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        self._assert_owner(doc.owner_id)
        doc = doc.model_copy(update={"search_index": build_document_search_index(doc)})
        # `original` é write-once: se já existe doc, manter original imutável.
        existing = self._documentos.get(doc.doc_id)
        if existing is not None:
            if existing.original != doc.original:
                msg = f"Tentativa de modificar `original` de doc {doc.doc_id} (write-once)"
                raise ValueError(msg)
            refreshed = existing.model_copy(
                update={
                    "schema_version": 2,
                    "search_index": build_document_search_index(existing),
                }
            )
            self._documentos[doc.doc_id] = refreshed.model_copy(deep=True)
            return
        self._documentos[doc.doc_id] = doc.model_copy(deep=True)

    async def get_documento(self, doc_id: str) -> Documento | None:
        doc = self._documentos.get(doc_id)
        return deepcopy(doc) if doc is not None else None

    async def list_documentos(
        self,
        *,
        since: datetime | None = None,
        status: StatusDocumento | None = None,
        uf: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Documento]:
        result = list(self._documentos.values())
        if since is not None:
            result = [d for d in result if d.original.fetched_at >= since]
        if status is not None:
            result = [d for d in result if d.status == status]
        if uf is not None:
            result = [d for d in result if d.source.uf == uf]
        result.sort(key=lambda d: d.original.fetched_at, reverse=True)
        return [deepcopy(d) for d in result[offset : offset + limit]]

    async def search_documentos(
        self,
        *,
        terms: list[str],
        uf: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
        scan_limit: int = 5000,
        include_archived: bool = False,
    ) -> list[Documento]:
        from monitoritcd.core.models import StatusDocumento  # noqa: PLC0415
        from monitoritcd.search import (  # noqa: PLC0415
            document_search_corpus,
            normalize_search_query,
        )

        docs = await self.list_documentos(since=since, uf=uf, limit=scan_limit)
        if not include_archived:
            docs = [doc for doc in docs if doc.status != StatusDocumento.ARCHIVED]
        normalized_terms = [normalize_search_query(term) for term in terms if term]
        if not normalized_terms:
            return docs[:limit]
        out: list[Documento] = []
        for doc in docs:
            corpus = document_search_corpus(doc).lower()
            if all(term in corpus for term in normalized_terms):
                out.append(doc)
                if len(out) >= limit:
                    break
        return out

    async def update_llm(self, doc_id: str, llm: LLMResult) -> None:
        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        doc = self._documentos.get(doc_id)
        if doc is None:
            msg = f"Documento não encontrado: {doc_id}"
            raise DocumentNotFoundError(msg)
        # Atualiza llm sem tocar em original (write-once)
        updated = doc.model_copy(update={"llm": llm})
        self._documentos[doc_id] = updated.model_copy(
            update={"schema_version": 2, "search_index": build_document_search_index(updated)}
        )

    async def update_notificacao(
        self,
        doc_id: str,
        notificacao: NotificacaoStatus,
    ) -> None:
        doc = self._documentos.get(doc_id)
        if doc is None:
            msg = f"Documento não encontrado: {doc_id}"
            raise DocumentNotFoundError(msg)
        self._documentos[doc_id] = doc.model_copy(update={"notificacao": notificacao})

    async def update_status(self, doc_id: str, status: StatusDocumento) -> None:
        doc = self._documentos.get(doc_id)
        if doc is None:
            msg = f"Documento não encontrado: {doc_id}"
            raise DocumentNotFoundError(msg)
        self._documentos[doc_id] = doc.model_copy(update={"status": status})

    async def update_search_index(self, doc_id: str) -> None:
        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        doc = self._documentos.get(doc_id)
        if doc is None:
            msg = f"Documento não encontrado: {doc_id}"
            raise DocumentNotFoundError(msg)
        self._documentos[doc_id] = doc.model_copy(
            update={"schema_version": 2, "search_index": build_document_search_index(doc)}
        )

    async def add_user_tag(self, doc_id: str, tag: str) -> None:
        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        doc = self._documentos.get(doc_id)
        if doc is None:
            msg = f"Documento não encontrado: {doc_id}"
            raise DocumentNotFoundError(msg)
        if tag in doc.user_tags:
            return  # idempotente
        new_tags = [*doc.user_tags, tag]
        updated = doc.model_copy(update={"user_tags": new_tags})
        self._documentos[doc_id] = updated.model_copy(
            update={"schema_version": 2, "search_index": build_document_search_index(updated)}
        )

    async def remove_user_tag(self, doc_id: str, tag: str) -> None:
        """V6 (Pentest): remoção atômica que preserva `original` write-once."""
        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        doc = self._documentos.get(doc_id)
        if doc is None:
            msg = f"Documento não encontrado: {doc_id}"
            raise DocumentNotFoundError(msg)
        if tag not in doc.user_tags:
            return  # idempotente
        new_tags = [t for t in doc.user_tags if t != tag]
        updated = doc.model_copy(update={"user_tags": new_tags})
        self._documentos[doc_id] = updated.model_copy(
            update={"schema_version": 2, "search_index": build_document_search_index(updated)}
        )

    async def exists_by_hash(self, content_hash: str) -> bool:
        return any(d.original.content_hash == content_hash for d in self._documentos.values())

    # ─── Active states ────────────────────────────────────────────────────

    async def get_active_states(self) -> ActiveStatesConfig | None:
        return deepcopy(self._active_states) if self._active_states else None

    async def save_active_states(self, config: ActiveStatesConfig) -> None:
        self._assert_owner(config.owner_id)
        self._active_states = config.model_copy(deep=True)

    # ─── Extra keywords (dinâmicas via /temas) ────────────────────────────

    async def get_extra_keywords(self) -> ExtraKeywordsConfig | None:
        return deepcopy(self._extra_keywords) if self._extra_keywords else None

    async def save_extra_keywords(self, config: ExtraKeywordsConfig) -> None:
        self._assert_owner(config.owner_id)
        self._extra_keywords = config.model_copy(deep=True)

    # ─── Extra topics (dinâmicos via /topicos) ────────────────────────────

    async def get_extra_topics(self) -> ExtraTopicsConfig | None:
        return deepcopy(self._extra_topics) if self._extra_topics else None

    async def save_extra_topics(self, config: ExtraTopicsConfig) -> None:
        self._assert_owner(config.owner_id)
        self._extra_topics = config.model_copy(deep=True)

    # ─── Watch list ───────────────────────────────────────────────────────

    async def save_watch(self, watch: Watch) -> None:
        self._assert_owner(watch.owner_id)
        self._watches[watch.watch_id] = watch.model_copy(deep=True)

    async def list_watches(self) -> list[Watch]:
        return [deepcopy(w) for w in self._watches.values()]

    async def delete_watch(self, watch_id: str) -> None:
        self._watches.pop(watch_id, None)

    # ─── Audit log ────────────────────────────────────────────────────────

    async def append_audit(self, entry: AuditLogEntry) -> None:
        self._assert_owner(entry.owner_id)
        # Verifica integridade da chain
        expected_prev = await self.get_last_audit_hash()
        if entry.prev_hash != expected_prev:
            msg = (
                f"hash chain quebrada: esperado prev_hash={expected_prev!r}, "
                f"recebido {entry.prev_hash!r}"
            )
            raise ValueError(msg)
        # Audit entries são frozen (model_config), append direto
        self._audit.append(entry)

    async def get_last_audit_hash(self) -> str:
        if not self._audit:
            return GENESIS_HASH
        last = self._audit[-1]
        # Hash da entry inteira: usado como prev_hash da próxima
        as_dict = last.model_dump(mode="json")
        canonical = json.dumps(as_dict, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def list_audit_recent(self, limit: int = 20) -> list[AuditLogEntry]:
        """Retorna últimas entries em ordem cronológica (Sugestão #25)."""
        return [deepcopy(e) for e in self._audit[-limit:]]
