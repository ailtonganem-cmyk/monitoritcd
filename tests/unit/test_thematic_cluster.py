"""Testes do cluster temático (Sugestão #50)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from monitoritcd.core.models import (
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
)
from monitoritcd.filters.thematic_cluster import (
    assign_thematic_clusters,
    multi_uf_clusters,
)


def _make_doc(
    *,
    doc_id: str,
    uf: str,
    topics: list[Topic],
    numero_ato: str | None = None,
) -> Documento:
    src = Source(
        id=f"src-{uf}",
        nome="Test",
        uf=uf,
        tipo=TipoFonte.NOTICIA,
        url="https://example.com/feed",
        parser=Parser.GENERIC_RSS,
        ativo=True,
        topics=[Topic.ITCD],
    )
    raw = RawItem(
        source_id=f"src-{uf}",
        url=f"https://example.com/{uf}",
        titulo_raw="T",
        texto_raw="Body",
        data_publicacao=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        content_hash="a" * 64,
    )
    metadados: dict[str, str] = {}
    if numero_ato:
        metadados["numero_ato"] = numero_ato
    llm = LLMResult(
        classified_at=datetime.now(UTC),
        llm_model="test",
        llm_prompt_version="v1.0",
        tipo=TipoAto.LEI_SANCIONADA,
        topics=topics,
        relevancia=8,
        severity_tier=SeverityTier.ALTA,
        resumo="Resumo factual de teste preservando dados originais.",
        metadados_extraidos=metadados,
    )
    return Documento(
        owner_id="o",
        doc_id=doc_id,
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )


@pytest.mark.unit
def test_clusters_same_topic_diff_uf() -> None:
    """Docs com mesmos topics + mesmo numero_ato em UFs distintas → 1 cluster."""
    docs = [
        _make_doc(doc_id="sp:x", uf="SP", topics=[Topic.ITCD], numero_ato="1234/2026"),
        _make_doc(doc_id="rj:x", uf="RJ", topics=[Topic.ITCD], numero_ato="1234/2026"),
    ]
    clusters = assign_thematic_clusters(docs)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.is_multi_uf
    assert set(cluster.ufs) == {"SP", "RJ"}


@pytest.mark.unit
def test_clusters_different_numero_ato() -> None:
    """Mesmo topic mas atos diferentes = clusters separados."""
    docs = [
        _make_doc(doc_id="sp:1", uf="SP", topics=[Topic.ITCD], numero_ato="1/2026"),
        _make_doc(doc_id="sp:2", uf="SP", topics=[Topic.ITCD], numero_ato="2/2026"),
    ]
    clusters = assign_thematic_clusters(docs)
    assert len(clusters) == 2


@pytest.mark.unit
def test_multi_uf_filter() -> None:
    """multi_uf_clusters retorna apenas clusters com 2+ UFs."""
    docs = [
        _make_doc(doc_id="sp:x", uf="SP", topics=[Topic.ITCD], numero_ato="1234/2026"),
        _make_doc(doc_id="rj:x", uf="RJ", topics=[Topic.ITCD], numero_ato="1234/2026"),
        _make_doc(doc_id="mg:y", uf="MG", topics=[Topic.SUCESSOES], numero_ato="999/2025"),
    ]
    multi = multi_uf_clusters(docs)
    assert len(multi) == 1
    assert set(multi[0].ufs) == {"SP", "RJ"}


@pytest.mark.unit
def test_no_topics_no_cluster() -> None:
    """Doc sem topics não entra em cluster."""
    docs = [_make_doc(doc_id="x", uf="SP", topics=[])]
    clusters = assign_thematic_clusters(docs)
    assert clusters == []


@pytest.mark.unit
def test_doc_without_llm_returns_none_numero() -> None:
    """Doc sem LLMResult não tem numero_ato extraído (linha 46 do módulo)."""
    from monitoritcd.filters.thematic_cluster import _doc_numero_ato  # noqa: PLC0415

    src = Source(
        id="src",
        nome="t",
        uf="SP",
        tipo=TipoFonte.NOTICIA,
        url="https://example.com/feed",
        parser=Parser.GENERIC_RSS,
        ativo=True,
        topics=[Topic.ITCD],
    )
    raw = RawItem(
        source_id="src",
        url="https://example.com/x",
        titulo_raw="T",
        texto_raw="B",
        data_publicacao=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        content_hash="a" * 64,
    )
    doc = Documento(
        owner_id="o",
        doc_id="x",
        source=src,
        original=raw,
        llm=None,
        status=StatusDocumento.PENDING,
    )
    assert _doc_numero_ato(doc) is None
