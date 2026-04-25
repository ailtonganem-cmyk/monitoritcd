"""Testes dos modelos pydantic.

Cobre:
- input_limits aplicados (Princípio Canônico 2)
- extra="forbid" rejeita campos desconhecidos (Princípio Canônico 1)
- owner_id obrigatório em OwnerScoped
- imutabilidade de RawItem (frozen=True)
- enums e literais
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from monitoritcd.core import limits
from monitoritcd.core.models import (
    ActiveStatesConfig,
    AuditLogEntry,
    BotCommand,
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

NOW = datetime.now(UTC)
SAMPLE_HASH = "a" * 64  # SHA-256 hex


def _make_source() -> Source:
    return Source(
        id="lexml-federal",
        uf="_federal",
        nome="LexML Federal",
        tipo=TipoFonte.JURISPRUDENCIA,
        parser=Parser.LEXML,
        url="https://www.lexml.gov.br/",
    )


def _make_raw() -> RawItem:
    return RawItem(
        source_id="lexml-federal",
        titulo_raw="PL 1234/2026 — ITCMD progressivo",
        url="https://example.gov.br/pl",
        fetched_at=NOW,
        content_hash=SAMPLE_HASH,
    )


@pytest.mark.unit
class TestSource:
    def test_valid_source(self) -> None:
        src = _make_source()
        assert src.id == "lexml-federal"
        assert src.uf == "_federal"
        assert src.ativo is True
        assert src.fragile is False

    def test_uf_pattern_rejects_invalid(self) -> None:
        with pytest.raises(ValidationError):
            Source(
                id="x",
                uf="sp",  # lowercase — inválido
                nome="X",
                tipo=TipoFonte.SEFAZ,
                parser=Parser.GENERIC_HTML,
                url="https://x.gov.br/",
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            Source(
                id="x",
                uf="SP",
                nome="X",
                tipo=TipoFonte.SEFAZ,
                parser=Parser.GENERIC_HTML,
                url="https://x.gov.br/",
                injected_attribute="malicious",
            )
        assert "injected_attribute" in str(exc.value)

    def test_url_max_length_enforced(self) -> None:
        with pytest.raises(ValidationError):
            Source(
                id="x",
                uf="SP",
                nome="X",
                tipo=TipoFonte.SEFAZ,
                parser=Parser.GENERIC_HTML,
                url="https://x.gov.br/" + "a" * limits.MAX_URL_LENGTH,
            )

    def test_keywords_max_items_enforced(self) -> None:
        with pytest.raises(ValidationError):
            Source(
                id="x",
                uf="SP",
                nome="X",
                tipo=TipoFonte.SEFAZ,
                parser=Parser.GENERIC_HTML,
                url="https://x.gov.br/",
                keywords_required=[f"kw{i}" for i in range(limits.MAX_KEYWORDS_LIST + 1)],
            )

    def test_source_is_frozen(self) -> None:
        src = _make_source()
        with pytest.raises(ValidationError):
            src.id = "modified"  # type: ignore[misc]


@pytest.mark.unit
class TestRawItem:
    def test_valid_raw_item(self) -> None:
        raw = _make_raw()
        assert raw.titulo_raw.startswith("PL 1234")
        assert raw.content_hash == SAMPLE_HASH

    def test_raw_item_is_frozen(self) -> None:
        raw = _make_raw()
        with pytest.raises(ValidationError):
            raw.titulo_raw = "modificado"  # type: ignore[misc]

    def test_titulo_max_length(self) -> None:
        with pytest.raises(ValidationError):
            RawItem(
                source_id="x",
                titulo_raw="x" * (limits.MAX_TITLE_LENGTH + 1),
                url="https://x.gov.br/",
                fetched_at=NOW,
                content_hash=SAMPLE_HASH,
            )

    def test_content_hash_must_be_64_hex(self) -> None:
        with pytest.raises(ValidationError):
            RawItem(
                source_id="x",
                titulo_raw="x",
                url="https://x.gov.br/",
                fetched_at=NOW,
                content_hash="too-short",
            )


@pytest.mark.unit
class TestLLMResult:
    def test_valid_llm_result(self) -> None:
        result = LLMResult(
            classified_at=NOW,
            llm_model="gemini-2.5-flash",
            llm_prompt_version="v1.0",
            tipo=TipoAto.PROJETO_LEI,
            relevancia=8,
            severity_tier=SeverityTier.ALTA,
            resumo="PL sobre ITCMD progressivo em SP.",
        )
        assert result.relevancia == 8

    def test_relevancia_must_be_in_range(self) -> None:
        with pytest.raises(ValidationError):
            LLMResult(
                classified_at=NOW,
                llm_model="x",
                llm_prompt_version="v1",
                tipo=TipoAto.OUTRO,
                relevancia=11,  # > MAX
                severity_tier=SeverityTier.NORMAL,
                resumo="x",
            )
        with pytest.raises(ValidationError):
            LLMResult(
                classified_at=NOW,
                llm_model="x",
                llm_prompt_version="v1",
                tipo=TipoAto.OUTRO,
                relevancia=-1,  # < MIN
                severity_tier=SeverityTier.NORMAL,
                resumo="x",
            )

    def test_resumo_respects_max_length(self) -> None:
        with pytest.raises(ValidationError):
            LLMResult(
                classified_at=NOW,
                llm_model="x",
                llm_prompt_version="v1",
                tipo=TipoAto.OUTRO,
                relevancia=5,
                severity_tier=SeverityTier.NORMAL,
                resumo="x" * (limits.MAX_SUMMARY_LENGTH + 1),
            )

    def test_tags_max_items(self) -> None:
        with pytest.raises(ValidationError):
            LLMResult(
                classified_at=NOW,
                llm_model="x",
                llm_prompt_version="v1",
                tipo=TipoAto.OUTRO,
                relevancia=5,
                severity_tier=SeverityTier.NORMAL,
                resumo="x",
                tags=[f"tag{i}" for i in range(limits.MAX_TAGS_PER_DOC + 1)],
            )


@pytest.mark.unit
class TestDocumento:
    def test_owner_id_required(self) -> None:
        with pytest.raises(ValidationError):
            Documento(
                doc_id="abc",
                source=_make_source(),
                original=_make_raw(),
                status=StatusDocumento.PENDING,
            )  # type: ignore[call-arg]

    def test_documento_with_all_fields(self) -> None:
        doc = Documento(
            owner_id="owner-alpha",
            doc_id="doc-001",
            source=_make_source(),
            original=_make_raw(),
            status=StatusDocumento.PENDING,
        )
        assert doc.owner_id == "owner-alpha"
        assert doc.notificacao.enviada is False
        assert doc.schema_version == 1


@pytest.mark.unit
class TestBotCommand:
    def test_command_max_length(self) -> None:
        with pytest.raises(ValidationError):
            BotCommand(
                chat_id=1,
                user_id=1,
                command="x" * (limits.MAX_BOT_COMMAND_LENGTH + 1),
                received_at=NOW,
            )

    def test_args_max_items(self) -> None:
        with pytest.raises(ValidationError):
            BotCommand(
                chat_id=1,
                user_id=1,
                command="/buscar",
                args=[f"a{i}" for i in range(11)],  # max=10
                received_at=NOW,
            )

    def test_arg_max_length(self) -> None:
        with pytest.raises(ValidationError):
            BotCommand(
                chat_id=1,
                user_id=1,
                command="/buscar",
                args=["x" * (limits.MAX_BOT_ARG_LENGTH + 1)],
                received_at=NOW,
            )


@pytest.mark.unit
class TestActiveStatesConfig:
    def test_active_uf_list_size(self) -> None:
        with pytest.raises(ValidationError):
            ActiveStatesConfig(
                owner_id="o",
                active_uf=["SP"] * (limits.MAX_ACTIVE_UFS + 1),
                updated_at=NOW,
                updated_by="bot",
            )

    def test_default_federal_active(self) -> None:
        cfg = ActiveStatesConfig(owner_id="o", active_uf=["SP"], updated_at=NOW, updated_by="bot")
        assert cfg.federal_active is True


@pytest.mark.unit
class TestWatch:
    def test_pattern_max_length(self) -> None:
        with pytest.raises(ValidationError):
            Watch(
                owner_id="o",
                watch_id="w1",
                pattern="x" * 501,
                pattern_type="term",
                created_at=NOW,
            )

    def test_cooldown_max_one_week(self) -> None:
        with pytest.raises(ValidationError):
            Watch(
                owner_id="o",
                watch_id="w1",
                pattern="x",
                pattern_type="term",
                cooldown_hours=169,  # > 168 (1 semana)
                created_at=NOW,
            )


@pytest.mark.unit
class TestAuditLogEntry:
    def test_entry_is_frozen(self) -> None:
        entry = AuditLogEntry(
            owner_id="o",
            entry_id="e1",
            timestamp=NOW,
            actor="bot:OWNER",
            action="states.activate",
            payload_hash="b" * 64,
            prev_hash="0" * 64,
            result="success",
        )
        with pytest.raises(ValidationError):
            entry.action = "tampered"  # type: ignore[misc]

    def test_hash_lengths_enforced(self) -> None:
        with pytest.raises(ValidationError):
            AuditLogEntry(
                owner_id="o",
                entry_id="e1",
                timestamp=NOW,
                actor="x",
                action="x",
                payload_hash="short",
                prev_hash="0" * 64,
                result="success",
            )


@pytest.mark.unit
def test_notificacao_status_default_factory_works() -> None:
    """Regression: NotificacaoStatus tem default_factory que cria instância vazia."""
    n = NotificacaoStatus()
    assert n.enviada is False
    assert n.canais == []
