"""Snapshot do schema Firestore (Sugestão #10).

Captura o shape de cada coleção como JSON. Mudanças não-intencionais quebram
o snapshot — força revisão.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from monitoritcd.core.models import (
    ActiveStatesConfig,
    Documento,
    LLMResult,
    Parser,
    RawItem,
    SeverityTier,
    Source,
    StatusDocumento,
    TipoAto,
    TipoFonte,
    Topic,
    Watch,
)


def _model_keys_recursive(model_dict: dict) -> dict:  # type: ignore[type-arg]
    """Captura apenas os keys e tipos (não valores) — schema-only snapshot."""
    out: dict = {}  # type: ignore[type-arg]
    for k, v in sorted(model_dict.items()):
        if isinstance(v, dict):
            out[k] = _model_keys_recursive(v)
        elif isinstance(v, list):
            out[k] = "list"
        else:
            out[k] = type(v).__name__
    return out


@pytest.fixture
def sample_source() -> Source:
    return Source(
        id="src1",
        nome="Test",
        uf="SP",
        tipo=TipoFonte.NOTICIA,
        url="https://example.com/feed",
        parser=Parser.GENERIC_RSS,
        ativo=True,
        topics=[Topic.ITCD],
    )


@pytest.fixture
def sample_raw_item() -> RawItem:
    return RawItem(
        source_id="src1",
        url="https://example.com/doc/1",
        titulo_raw="Test Title",
        texto_raw="Body",
        data_publicacao=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        content_hash="a" * 64,
    )


@pytest.mark.unit
def test_documento_schema_snapshot(
    snapshot, sample_source: Source, sample_raw_item: RawItem
) -> None:  # type: ignore[no-untyped-def]
    """Schema do Documento (raiz da coleção `documento/`)."""
    llm = LLMResult(
        classified_at=datetime.now(UTC),
        llm_model="gemini-2.5-flash",
        llm_prompt_version="v1.0",
        tipo=TipoAto.LEI_SANCIONADA,
        topics=[Topic.ITCD],
        relevancia=8,
        severity_tier=SeverityTier.ALTA,
        resumo="Resumo factual de teste preservando dados originais.",
    )
    doc = Documento(
        owner_id="o",
        doc_id="src1:abc",
        source=sample_source,
        original=sample_raw_item,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )
    schema = _model_keys_recursive(doc.model_dump(mode="json"))
    assert schema == snapshot


@pytest.mark.unit
def test_active_states_schema_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    """Schema de active_states (config raiz)."""
    cfg = ActiveStatesConfig(
        owner_id="o",
        active_uf=["SP"],
        federal_active=True,
        updated_at=datetime.now(UTC),
        updated_by="test",
    )
    schema = _model_keys_recursive(cfg.model_dump(mode="json"))
    assert schema == snapshot


@pytest.mark.unit
def test_watch_schema_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    """Schema de watch."""
    w = Watch(
        owner_id="o",
        watch_id="abcd1234",
        pattern="ITCD",
        pattern_type="term",
        relevancia_min=5,
        created_at=datetime.now(UTC),
    )
    schema = _model_keys_recursive(w.model_dump(mode="json"))
    assert schema == snapshot
