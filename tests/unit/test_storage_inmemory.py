"""Testes do `InMemoryStorage` — backend de testes do storage.

Verifica:
- owner_id assertion em mutations
- write-once de `original` (RawItem imutável)
- audit log com hash chain válida
- queries (since, status, uf) corretas
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from monitoritcd.core.models import (
    ActiveStatesConfig,
    Documento,
    LLMResult,
    NotificacaoStatus,
    Parser,
    RawItem,
    SeverityTier,
    Source,
    StatusDocumento,
    TipoAto,
    TipoFonte,
    Watch,
)
from monitoritcd.storage import InMemoryStorage, OwnershipError
from monitoritcd.storage.audit_log import AuditChainError, AuditLog
from monitoritcd.storage.in_memory import GENESIS_HASH, DocumentNotFoundError

NOW = datetime.now(UTC)
HASH = "a" * 64
OWNER = "owner-test"


def _src(uf: str = "SP") -> Source:
    return Source(
        id=f"src-{uf}",
        uf=uf,
        nome="x",
        tipo=TipoFonte.SEFAZ,
        parser=Parser.GENERIC_HTML,
        url=f"https://x{uf}.gov.br/",
    )


def _raw(content_hash: str = HASH) -> RawItem:
    return RawItem(
        source_id="src-SP",
        titulo_raw="ITCMD",
        url="https://x.gov.br/i",
        fetched_at=NOW,
        content_hash=content_hash,
    )


def _doc(
    *,
    doc_id: str = "doc1",
    owner: str = OWNER,
    status: StatusDocumento = StatusDocumento.PENDING,
    uf: str = "SP",
    content_hash: str = HASH,
    fetched_at: datetime | None = None,
) -> Documento:
    raw = RawItem(
        source_id=f"src-{uf}",
        titulo_raw="x",
        url="https://x.gov.br/i",
        fetched_at=fetched_at or NOW,
        content_hash=content_hash,
    )
    return Documento(
        owner_id=owner,
        doc_id=doc_id,
        source=_src(uf),
        original=raw,
        status=status,
    )


def _llm() -> LLMResult:
    return LLMResult(
        classified_at=NOW,
        llm_model="test",
        llm_prompt_version="v1",
        tipo=TipoAto.NOTICIA,
        relevancia=7,
        severity_tier=SeverityTier.NORMAL,
        resumo="x",
    )


@pytest.mark.unit
class TestSaveDocumento:
    @pytest.mark.asyncio
    async def test_saves_and_retrieves(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.save_documento(_doc())
        retrieved = await s.get_documento("doc1")
        assert retrieved is not None
        assert retrieved.doc_id == "doc1"

    @pytest.mark.asyncio
    async def test_owner_mismatch_rejected(self) -> None:
        s = InMemoryStorage(OWNER)
        wrong = _doc(owner="other-owner")
        with pytest.raises(OwnershipError):
            await s.save_documento(wrong)

    @pytest.mark.asyncio
    async def test_get_unknown_returns_none(self) -> None:
        s = InMemoryStorage(OWNER)
        assert await s.get_documento("missing") is None

    @pytest.mark.asyncio
    async def test_original_is_write_once(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.save_documento(_doc(content_hash="a" * 64))
        # Tentativa de modificar `original` (mesmo doc_id, raw diferente) → erro
        modified = _doc(content_hash="b" * 64)
        with pytest.raises(ValueError, match="write-once"):
            await s.save_documento(modified)

    @pytest.mark.asyncio
    async def test_idempotent_when_original_unchanged(self) -> None:
        s = InMemoryStorage(OWNER)
        doc = _doc()
        await s.save_documento(doc)
        # Re-save com mesmo conteúdo é idempotente
        await s.save_documento(doc)


@pytest.mark.unit
class TestListDocumentos:
    @pytest.mark.asyncio
    async def test_filter_by_status(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.save_documento(_doc(doc_id="a", status=StatusDocumento.PENDING))
        await s.save_documento(_doc(doc_id="b", status=StatusDocumento.NOTIFIED))
        result = await s.list_documentos(status=StatusDocumento.NOTIFIED)
        assert len(result) == 1
        assert result[0].doc_id == "b"

    @pytest.mark.asyncio
    async def test_filter_by_uf(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.save_documento(_doc(doc_id="sp", uf="SP"))
        await s.save_documento(_doc(doc_id="rj", uf="RJ"))
        result = await s.list_documentos(uf="SP")
        assert len(result) == 1
        assert result[0].source.uf == "SP"

    @pytest.mark.asyncio
    async def test_filter_by_since(self) -> None:
        s = InMemoryStorage(OWNER)
        old = _doc(doc_id="old", fetched_at=NOW - timedelta(days=10))
        new = _doc(doc_id="new", fetched_at=NOW)
        await s.save_documento(old)
        await s.save_documento(new)
        result = await s.list_documentos(since=NOW - timedelta(days=1))
        assert len(result) == 1
        assert result[0].doc_id == "new"

    @pytest.mark.asyncio
    async def test_limit(self) -> None:
        s = InMemoryStorage(OWNER)
        for i in range(5):
            await s.save_documento(_doc(doc_id=f"d{i}", content_hash=("a" + str(i)) * 32))
        result = await s.list_documentos(limit=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_sorted_descending_by_fetched_at(self) -> None:
        s = InMemoryStorage(OWNER)
        old = _doc(doc_id="old", fetched_at=NOW - timedelta(days=2), content_hash="0" * 64)
        new = _doc(doc_id="new", fetched_at=NOW, content_hash="1" * 64)
        await s.save_documento(old)
        await s.save_documento(new)
        result = await s.list_documentos()
        assert result[0].doc_id == "new"


@pytest.mark.unit
class TestUpdates:
    @pytest.mark.asyncio
    async def test_update_llm(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.save_documento(_doc())
        await s.update_llm("doc1", _llm())
        retrieved = await s.get_documento("doc1")
        assert retrieved is not None
        assert retrieved.llm is not None
        assert retrieved.llm.relevancia == 7

    @pytest.mark.asyncio
    async def test_update_unknown_doc_raises(self) -> None:
        s = InMemoryStorage(OWNER)
        with pytest.raises(DocumentNotFoundError):
            await s.update_llm("missing", _llm())

    @pytest.mark.asyncio
    async def test_update_status(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.save_documento(_doc())
        await s.update_status("doc1", StatusDocumento.NOTIFIED)
        retrieved = await s.get_documento("doc1")
        assert retrieved is not None
        assert retrieved.status == StatusDocumento.NOTIFIED

    @pytest.mark.asyncio
    async def test_update_notificacao(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.save_documento(_doc())
        notif = NotificacaoStatus(enviada=True, enviada_em=NOW, canais=["telegram"])
        await s.update_notificacao("doc1", notif)
        retrieved = await s.get_documento("doc1")
        assert retrieved is not None
        assert retrieved.notificacao.enviada is True

    @pytest.mark.asyncio
    async def test_update_notificacao_unknown_raises(self) -> None:
        s = InMemoryStorage(OWNER)
        with pytest.raises(DocumentNotFoundError):
            await s.update_notificacao("missing", NotificacaoStatus())

    @pytest.mark.asyncio
    async def test_update_status_unknown_raises(self) -> None:
        s = InMemoryStorage(OWNER)
        with pytest.raises(DocumentNotFoundError):
            await s.update_status("missing", StatusDocumento.NOTIFIED)


@pytest.mark.unit
class TestExistsByHash:
    @pytest.mark.asyncio
    async def test_returns_true_when_present(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.save_documento(_doc(content_hash="h" * 64))
        assert await s.exists_by_hash("h" * 64)

    @pytest.mark.asyncio
    async def test_returns_false_when_absent(self) -> None:
        s = InMemoryStorage(OWNER)
        assert not await s.exists_by_hash("z" * 64)


@pytest.mark.unit
class TestActiveStates:
    @pytest.mark.asyncio
    async def test_save_and_load(self) -> None:
        s = InMemoryStorage(OWNER)
        cfg = ActiveStatesConfig(
            owner_id=OWNER,
            active_uf=["SP", "RJ"],
            updated_at=NOW,
            updated_by="bot",
        )
        await s.save_active_states(cfg)
        loaded = await s.get_active_states()
        assert loaded is not None
        assert loaded.active_uf == ["SP", "RJ"]

    @pytest.mark.asyncio
    async def test_get_returns_none_when_unset(self) -> None:
        s = InMemoryStorage(OWNER)
        assert await s.get_active_states() is None

    @pytest.mark.asyncio
    async def test_owner_mismatch_rejected(self) -> None:
        s = InMemoryStorage(OWNER)
        wrong = ActiveStatesConfig(
            owner_id="other",
            active_uf=["SP"],
            updated_at=NOW,
            updated_by="bot",
        )
        with pytest.raises(OwnershipError):
            await s.save_active_states(wrong)


@pytest.mark.unit
class TestWatches:
    @pytest.mark.asyncio
    async def test_save_list_delete(self) -> None:
        s = InMemoryStorage(OWNER)
        w = Watch(
            owner_id=OWNER,
            watch_id="w1",
            pattern="ITCMD",
            pattern_type="term",
            created_at=NOW,
        )
        await s.save_watch(w)
        watches = await s.list_watches()
        assert len(watches) == 1
        assert watches[0].watch_id == "w1"
        await s.delete_watch("w1")
        assert await s.list_watches() == []

    @pytest.mark.asyncio
    async def test_delete_nonexistent_no_error(self) -> None:
        s = InMemoryStorage(OWNER)
        await s.delete_watch("missing")  # silencioso


@pytest.mark.unit
class TestAuditLog:
    @pytest.mark.asyncio
    async def test_first_audit_uses_genesis_prev_hash(self) -> None:
        s = InMemoryStorage(OWNER)
        log = AuditLog(s)
        entry = await log.append(actor="bot", action="test", payload={"k": "v"})
        assert entry.prev_hash == GENESIS_HASH

    @pytest.mark.asyncio
    async def test_chain_continues(self) -> None:
        s = InMemoryStorage(OWNER)
        log = AuditLog(s)
        e1 = await log.append(actor="bot", action="a1", payload={"k": 1})
        e2 = await log.append(actor="bot", action="a2", payload={"k": 2})
        # prev_hash de e2 deve ser hash de e1
        assert e2.prev_hash != GENESIS_HASH
        assert e2.prev_hash != e1.prev_hash

    @pytest.mark.asyncio
    async def test_verify_chain_valid(self) -> None:
        s = InMemoryStorage(OWNER)
        log = AuditLog(s)
        await log.append(actor="bot", action="a", payload={})
        await log.append(actor="bot", action="b", payload={})
        await log.verify_chain(s._audit)

    @pytest.mark.asyncio
    async def test_verify_chain_detects_tampering(self) -> None:
        s = InMemoryStorage(OWNER)
        log = AuditLog(s)
        await log.append(actor="bot", action="a", payload={"k": "v1"})
        await log.append(actor="bot", action="b", payload={"k": "v2"})
        # Adultera entry no meio: substituir por entry com prev_hash inválido
        from monitoritcd.core.models import AuditLogEntry  # noqa: PLC0415

        s._audit[1] = AuditLogEntry(
            owner_id=OWNER,
            entry_id="tampered",
            timestamp=NOW,
            actor="x",
            action="x",
            payload_hash="z" * 64,
            prev_hash="z" * 64,  # hash falsa quebra a chain
            result="success",
        )
        with pytest.raises(AuditChainError):
            await log.verify_chain(s._audit)
