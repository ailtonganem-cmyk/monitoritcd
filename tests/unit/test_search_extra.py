"""Cobertura adicional de `search.py` (linhas/branches faltantes)."""

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
from monitoritcd.search import (
    _parse_period,
    boolean_search,
    faceted_search,
)


def _doc(
    *,
    doc_id: str = "x",
    uf: str = "SP",
    titulo: str = "Lei sobre ITCD",
    relevancia: int = 8,
) -> Documento:
    src = Source(
        id="src1",
        nome="Test",
        uf=uf,
        tipo=TipoFonte.NOTICIA,
        url="https://example.com/feed",
        parser=Parser.GENERIC_RSS,
        ativo=True,
        topics=[Topic.ITCD],
    )
    raw = RawItem(
        source_id="src1",
        url=f"https://example.com/{doc_id}",
        titulo_raw=titulo,
        texto_raw="Body com ITCD",
        data_publicacao=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
        content_hash="a" * 64,
    )
    llm = LLMResult(
        classified_at=datetime.now(UTC),
        llm_model="gemini",
        llm_prompt_version="v1.0",
        tipo=TipoAto.LEI_SANCIONADA,
        topics=[Topic.ITCD],
        relevancia=relevancia,
        severity_tier=SeverityTier.ALTA,
        resumo="Resumo factual de teste.",
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
def test_faceted_search_uf_filter() -> None:
    docs = [_doc(doc_id="sp1", uf="SP"), _doc(doc_id="rj1", uf="RJ")]
    result = faceted_search(docs, uf="SP")
    assert len(result) == 1
    assert result[0].doc_id == "sp1"


@pytest.mark.unit
def test_faceted_search_relevancia_min() -> None:
    docs = [
        _doc(doc_id="low", relevancia=3),
        _doc(doc_id="high", relevancia=9),
    ]
    result = faceted_search(docs, relevancia_min=8)
    assert {d.doc_id for d in result} == {"high"}


@pytest.mark.unit
def test_faceted_search_llm_model_filter() -> None:
    docs = [_doc()]
    result = faceted_search(docs, llm_model="gemini")
    assert len(result) == 1
    result_no_match = faceted_search(docs, llm_model="claude")
    assert result_no_match == []


@pytest.mark.unit
def test_faceted_search_prompt_version_filter() -> None:
    docs = [_doc()]
    result = faceted_search(docs, prompt_version="v1.0")
    assert len(result) == 1


@pytest.mark.unit
def test__parse_period_mes_ano() -> None:
    """Reconhece 'abril 2026'."""
    dt = _parse_period("abril 2026")
    assert dt is not None
    assert dt.month == 4
    assert dt.year == 2026


@pytest.mark.unit
def test__parse_period_quarter() -> None:
    """Reconhece 'Q2 2026' = abril/2026."""
    dt = _parse_period("Q2 2026")
    assert dt is not None
    assert dt.month == 4
    assert dt.year == 2026


@pytest.mark.unit
def test__parse_period_iso_full() -> None:
    """Reconhece 2026-04-15."""
    dt = _parse_period("2026-04-15")
    assert dt is not None
    assert dt.day == 15


@pytest.mark.unit
def test__parse_period_invalid() -> None:
    assert _parse_period("nada disso") is None


@pytest.mark.unit
def test_boolean_search_simple() -> None:
    docs = [
        _doc(doc_id="itcd-doc", titulo="ITCD novo"),
        _doc(doc_id="other", titulo="outra coisa"),
    ]
    # Termo simples
    result = boolean_search(docs, "ITCD")
    assert any(d.doc_id == "itcd-doc" for d in result)
