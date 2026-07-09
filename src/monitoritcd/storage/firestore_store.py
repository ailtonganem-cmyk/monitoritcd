"""Backend Firestore real (produção).

Implementa `StorageProtocol` usando google-cloud-firestore async client.
Aplica `owner_id` assertion e queries scoped por owner em todas operações.

NOTA: testes unitários usam `InMemoryStorage`. Este backend é validado por
testes integration com Firebase emulator (Fase 9 do PLAN.md).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from monitoritcd.core.models import (
    ActiveStatesConfig,
    AuditLogEntry,
    Documento,
    ExtraKeywordsConfig,
    ExtraTopicsConfig,
    NotificacaoStatus,
    StatusDocumento,
    Watch,
)
from monitoritcd.storage.audit_log import OwnershipError
from monitoritcd.storage.in_memory import GENESIS_HASH

if TYPE_CHECKING:
    from google.cloud.firestore import AsyncClient

    from monitoritcd.core.models import LLMResult
    from monitoritcd.orchestrator import RunReport

logger = structlog.get_logger(__name__)

# Coleções (prefixo `monitor_` — Firestore compartilhado com outro projeto)
COLLECTION_DOCUMENTOS = "monitor_documentos"
COLLECTION_ACTIVE_STATES = "monitor_config"
COLLECTION_WATCHES = "monitor_watches"
COLLECTION_AUDIT = "monitor_audit_log"
COLLECTION_RUNS = "monitor_runs"
COLLECTION_SUBSCRIPTIONS = "monitor_subscriptions"


def _dt_to_stored(value: datetime) -> str:
    """Converte `datetime` para o MESMO formato string gravado no Firestore.

    `save_documento` (e todo `model_dump(mode="json")` do pydantic) serializa
    `datetime` como ISO 8601 UTC com sufixo "Z" — SEM fração de segundo quando
    `microsecond == 0`, e com 6 dígitos quando != 0 (comportamento nativo do
    pydantic-core, não custom). Comparar um `datetime` Python direto contra
    esse campo (que é STRING no Firestore) nunca casa — tipos diferentes não
    são comparáveis no Firestore, e o filtro `where(..., ">=", datetime)`
    retorna sempre vazio, silenciosamente.

    Esta função sempre emite 6 dígitos de microssegundos (nunca omite a
    fração), mesmo quando `value.microsecond == 0`. Isso é proposital: um
    filtro `since` construído a partir de uma data "seca" (`YYYY-MM-DD` →
    meia-noite, microsecond=0) deve continuar comparando como o LIMITE
    INFERIOR daquele segundo. Se omitíssemos a fração nesse caso, o filtro
    produziria a string "...T00:00:00Z" (termina em "Z", 0x5A), que é
    lexicograficamente MAIOR que "...T00:00:00.304171Z" (termina em ".",
    0x2E) — excluindo incorretamente documentos gravados no mesmo segundo com
    microssegundos > 0. Sempre emitir ".000000Z" evita essa armadilha: o
    filtro fica <= qualquer serialização possível (com ou sem fração) daquele
    mesmo segundo, então nunca exclui um documento que deveria entrar.

    Risco residual (documentado, não corrigido aqui): se o PRÓPRIO `since`
    tiver microssegundos > 0 e um documento gravado tiver microsecond == 0 no
    mesmo segundo (evento raríssimo — datetime.now() cair exatamente em
    micro=0), a comparação pode incluir esse documento mesmo que seu instante
    real seja anterior a `since`. É um falso positivo (inclui demais), nunca
    um falso negativo (nunca omite silenciosamente) — a classe de erro que
    este fix corrige é a oposta (exclusão total e silenciosa).
    """
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


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
        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        self._assert_owner(doc.owner_id)
        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc.doc_id)
        snapshot = await ref.get()
        if snapshot.exists:
            data = snapshot.to_dict() or {}
            self._assert_owner(data.get("owner_id", ""))
            existing = Documento(**data)
            if existing.original != doc.original:
                msg = f"Tentativa de modificar `original` de doc {doc.doc_id} (write-once)"
                raise ValueError(msg)
            await ref.update(
                {
                    "schema_version": 2,
                    "search_index": build_document_search_index(existing).model_dump(mode="json"),
                }
            )
            return
        doc = doc.model_copy(update={"search_index": build_document_search_index(doc)})
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
        offset: int = 0,
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
            query = query.where("original.fetched_at", ">=", _dt_to_stored(since))
        query = (
            query.order_by("original.fetched_at", direction="DESCENDING")
            .offset(offset)
            .limit(limit)
        )

        results: list[Documento] = []
        async for snapshot in query.stream():
            data = snapshot.to_dict()
            if data and data.get("owner_id") == self._owner_id:
                results.append(Documento(**data))
        return results

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
        from monitoritcd.search import (  # noqa: PLC0415
            document_search_corpus,
            normalize_search_query,
            search_terms_for_query,
        )

        normalized_terms = [normalize_search_query(term) for term in terms if term]
        index_terms = search_terms_for_query(terms)
        if index_terms:
            return await self._search_documentos_by_index(
                index_terms=index_terms,
                normalized_terms=normalized_terms,
                uf=uf,
                since=since,
                limit=limit,
                scan_limit=scan_limit,
                include_archived=include_archived,
            )
        docs = await self.list_documentos(since=since, uf=uf, limit=scan_limit)
        if not include_archived:
            docs = [doc for doc in docs if doc.status != StatusDocumento.ARCHIVED]
        if not normalized_terms:
            return docs[:limit]
        results: list[Documento] = []
        for doc in docs:
            corpus = document_search_corpus(doc).lower()
            if all(term in corpus for term in normalized_terms):
                results.append(doc)
                if len(results) >= limit:
                    break
        return results

    async def _search_documentos_by_index(
        self,
        *,
        index_terms: list[str],
        normalized_terms: list[str],
        uf: str | None,
        since: datetime | None,
        limit: int,
        scan_limit: int,
        include_archived: bool,
    ) -> list[Documento]:
        from monitoritcd.search import document_search_corpus  # noqa: PLC0415

        primary_candidates = [term for term in index_terms if " " not in term]
        primary_term = max(primary_candidates or index_terms, key=len)
        query: Any = (
            self._client.collection(COLLECTION_DOCUMENTOS)
            .where("owner_id", "==", self._owner_id)
            .where("search_index.terms", "array_contains", primary_term)
        )
        if uf is not None:
            query = query.where("source.uf", "==", uf)
        if since is not None:
            query = query.where("original.fetched_at", ">=", _dt_to_stored(since))
        query = query.order_by("original.fetched_at", direction="DESCENDING")

        docs: list[Documento] = []
        page_size = max(1, min(scan_limit, 500))
        offset = 0
        while len(docs) < limit:
            page_query = query.offset(offset).limit(page_size)
            page_seen = 0
            async for snapshot in page_query.stream():
                page_seen += 1
                data = snapshot.to_dict()
                if not data or data.get("owner_id") != self._owner_id:
                    continue
                doc = Documento(**data)
                if not include_archived and doc.status == StatusDocumento.ARCHIVED:
                    continue
                corpus = document_search_corpus(doc).lower()
                if normalized_terms and not all(term in corpus for term in normalized_terms):
                    continue
                docs.append(doc)
                if len(docs) >= limit:
                    break
            if page_seen < page_size or len(docs) >= limit:
                break
            offset += page_seen
        return docs

    async def update_llm(self, doc_id: str, llm: LLMResult) -> None:
        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc_id)
        # Read-validate-write para garantir owner check
        snapshot = await ref.get()
        if not snapshot.exists:
            msg = f"Documento não encontrado: {doc_id}"
            raise ValueError(msg)
        data = snapshot.to_dict() or {}
        self._assert_owner(data.get("owner_id", ""))
        updated_doc = Documento(**data).model_copy(update={"llm": llm})
        search_index = build_document_search_index(updated_doc)
        await ref.update(
            {
                "schema_version": 2,
                "llm": llm.model_dump(mode="json"),
                "search_index": search_index.model_dump(mode="json"),
            }
        )

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

    async def update_search_index(self, doc_id: str) -> None:
        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc_id)
        snapshot = await ref.get()
        if not snapshot.exists:
            msg = f"Documento não encontrado: {doc_id}"
            raise ValueError(msg)
        data = snapshot.to_dict() or {}
        self._assert_owner(data.get("owner_id", ""))
        doc = Documento(**data)
        search_index = build_document_search_index(doc)
        await ref.update(
            {"schema_version": 2, "search_index": search_index.model_dump(mode="json")}
        )

    async def add_user_tag(self, doc_id: str, tag: str) -> None:
        """V6 (Pentest): adiciona tag preservando `original` write-once."""
        from google.cloud.firestore import async_transactional  # noqa: PLC0415

        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc_id)
        transaction = self._client.transaction()

        @async_transactional
        async def _add_in_transaction(transaction: object) -> None:
            snapshot = await ref.get(transaction=transaction)
            if not snapshot.exists:
                msg = f"Documento não encontrado: {doc_id}"
                raise ValueError(msg)
            data = snapshot.to_dict() or {}
            self._assert_owner(data.get("owner_id", ""))
            doc = Documento(**data)
            new_tags = [*doc.user_tags, tag] if tag not in doc.user_tags else doc.user_tags
            updated = doc.model_copy(update={"user_tags": new_tags})
            transaction.update(
                ref,
                {
                    "schema_version": 2,
                    "user_tags": new_tags,
                    "search_index": build_document_search_index(updated).model_dump(mode="json"),
                },
            )

        await _add_in_transaction(transaction)

    async def remove_user_tag(self, doc_id: str, tag: str) -> None:
        """V6 (Pentest): remove tag preservando `original` write-once."""
        from google.cloud.firestore import async_transactional  # noqa: PLC0415

        from monitoritcd.search import build_document_search_index  # noqa: PLC0415

        ref = self._client.collection(COLLECTION_DOCUMENTOS).document(doc_id)
        transaction = self._client.transaction()

        @async_transactional
        async def _remove_in_transaction(transaction: object) -> None:
            snapshot = await ref.get(transaction=transaction)
            if not snapshot.exists:
                msg = f"Documento não encontrado: {doc_id}"
                raise ValueError(msg)
            data = snapshot.to_dict() or {}
            self._assert_owner(data.get("owner_id", ""))
            doc = Documento(**data)
            new_tags = [t for t in doc.user_tags if t != tag]
            updated = doc.model_copy(update={"user_tags": new_tags})
            transaction.update(
                ref,
                {
                    "schema_version": 2,
                    "user_tags": new_tags,
                    "search_index": build_document_search_index(updated).model_dump(mode="json"),
                },
            )

        await _remove_in_transaction(transaction)

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

    # ─── Extra keywords (dinâmicas via /temas) ────────────────────────────

    async def get_extra_keywords(self) -> ExtraKeywordsConfig | None:
        ref = self._client.collection(COLLECTION_ACTIVE_STATES).document("extra_keywords")
        snapshot = await ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data is None:  # pragma: no cover
            return None
        if data.get("owner_id") != self._owner_id:
            self._assert_owner(data.get("owner_id", ""))
        return ExtraKeywordsConfig(**data)

    async def save_extra_keywords(self, config: ExtraKeywordsConfig) -> None:
        self._assert_owner(config.owner_id)
        ref = self._client.collection(COLLECTION_ACTIVE_STATES).document("extra_keywords")
        await ref.set(config.model_dump(mode="json"))

    # ─── Extra topics (dinâmicos via /topicos) ────────────────────────────

    async def get_extra_topics(self) -> ExtraTopicsConfig | None:
        ref = self._client.collection(COLLECTION_ACTIVE_STATES).document("extra_topics")
        snapshot = await ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data is None:  # pragma: no cover
            return None
        if data.get("owner_id") != self._owner_id:
            self._assert_owner(data.get("owner_id", ""))
        return ExtraTopicsConfig(**data)

    async def save_extra_topics(self, config: ExtraTopicsConfig) -> None:
        self._assert_owner(config.owner_id)
        ref = self._client.collection(COLLECTION_ACTIVE_STATES).document("extra_topics")
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

    async def list_email_subscribers(self) -> list[str]:
        """E-mails de usuários com opt-in ativo em `monitor_subscriptions`.

        Coleção externa (gravada pelo app SEFWorkStation via Admin SDK), não
        owner-scoped deste pipeline. Descarta e-mails vazios/duplicados.
        """
        query = self._client.collection(COLLECTION_SUBSCRIPTIONS).where(
            "emailOptin",
            "==",
            True,
        )
        emails: list[str] = []
        seen: set[str] = set()
        async for snapshot in query.stream():
            data = snapshot.to_dict()
            if not data:
                continue
            email = data.get("email")
            if isinstance(email, str) and email.strip() and email not in seen:
                seen.add(email)
                emails.append(email)
        return emails

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

    # ─── Run reports ──────────────────────────────────────────────────────

    async def save_run_report(self, report: RunReport) -> None:
        """Persiste o `RunReport` de uma execução do orquestrador em `monitor_runs`.

        `started_at`/`finished_at` são gravados como ISO string via
        `_dt_to_stored` — a MESMA convenção de `save_documento` (pydantic-JSON)
        e da query de retenção em `scripts/cleanup_retention.py`
        (`.where("started_at", "<", _dt_to_stored(cutoff))`). Manter o formato
        idêntico dos dois lados é o que faz o filtro de purga casar (Firestore
        não compara string com Timestamp, silenciosamente) e alinha todas as
        coleções `monitor_*` no mesmo formato de data. `finished_at` pode ser
        None (run interrompido antes de concluir) — nesse caso não passa pelo
        helper, que não trata None.
        """
        from dataclasses import asdict  # noqa: PLC0415

        data = asdict(report)
        data["duration_seconds"] = report.duration_seconds
        data["owner_id"] = self._owner_id
        data["started_at"] = _dt_to_stored(report.started_at)
        data["finished_at"] = (
            _dt_to_stored(report.finished_at) if report.finished_at is not None else None
        )
        ref = self._client.collection(COLLECTION_RUNS).document(report.run_id)
        await ref.set(data)
