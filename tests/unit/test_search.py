"""Testes do módulo search (Categoria 8 IDEAS.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
)
from monitoritcd.search import (
    MAX_QUERY_LENGTH,
    boolean_search,
    faceted_search,
    fuzzy_search,
    highlight_term,
    more_like_this,
    normalize_act_number,
    regex_search,
)

NOW = datetime.now(UTC)


def _doc(
    *,
    titulo: str = "Lei sobre ITCMD",
    uf: str = "SP",
    age_days: int = 0,
    relev: int = 7,
    tipo: TipoAto = TipoAto.PROJETO_LEI,
    tier: SeverityTier = SeverityTier.NORMAL,
    resumo: str = "resumo padrao",
    user_tags: list[str] | None = None,
    doc_id: str = "d1",
    llm_model: str = "gemini-2.5-flash",
    prompt_version: str = "v1.0",
) -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw=titulo,
        url=f"https://x.gov.br/{doc_id}",
        fetched_at=NOW,
        data_publicacao=NOW - timedelta(days=age_days),
        content_hash="a" * 64,
    )
    src = Source(
        id="src",
        uf=uf,
        nome="ALESP",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = LLMResult(
        classified_at=NOW,
        llm_model=llm_model,
        llm_prompt_version=prompt_version,
        tipo=tipo,
        relevancia=relev,
        severity_tier=tier,
        resumo=resumo,
    )
    return Documento(
        owner_id="o",
        doc_id=doc_id,
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
        user_tags=user_tags or [],
    )


@pytest.mark.unit
class TestNormalizeAct:
    def test_lei_no_format_padrao(self) -> None:
        assert normalize_act_number("Lei nº 14.123/2024") == "14123/2024"

    def test_lei_separador_virgula(self) -> None:
        assert normalize_act_number("Lei 1.234, de 2026") == "1234/2026"

    def test_sem_match(self) -> None:
        assert normalize_act_number("Texto neutro") is None


@pytest.mark.unit
class TestFaceted:
    def test_uf_filter(self) -> None:
        docs = [_doc(uf="SP", doc_id="a"), _doc(uf="RJ", doc_id="b")]
        result = faceted_search(docs, uf="SP")
        assert len(result) == 1
        assert result[0].doc_id == "a"

    def test_term_filter(self) -> None:
        docs = [
            _doc(titulo="Lei sobre ITCMD progressivo", doc_id="a"),
            _doc(titulo="Decreto sobre algo", doc_id="b"),
        ]
        result = faceted_search(docs, term="itcmd")
        assert len(result) == 1
        assert result[0].doc_id == "a"

    def test_relevancia_min(self) -> None:
        docs = [
            _doc(relev=3, doc_id="low"),
            _doc(relev=8, doc_id="hi"),
        ]
        result = faceted_search(docs, relevancia_min=7)
        assert len(result) == 1
        assert result[0].doc_id == "hi"

    def test_period_relativo(self) -> None:
        docs = [
            _doc(age_days=2, doc_id="recente"),
            _doc(age_days=60, doc_id="velho"),
        ]
        result = faceted_search(docs, period="30d")
        ids = {d.doc_id for d in result}
        assert "recente" in ids
        assert "velho" not in ids

    def test_period_iso_yyyy_mm(self) -> None:
        # Bucket do mês atual
        cur_month = NOW.strftime("%Y-%m")
        docs = [_doc(doc_id="recente")]
        result = faceted_search(docs, period=cur_month)
        assert len(result) == 1

    def test_tag_filter(self) -> None:
        docs = [
            _doc(doc_id="a", user_tags=["favorito"]),
            _doc(doc_id="b", user_tags=[]),
        ]
        result = faceted_search(docs, tag="favorito")
        assert len(result) == 1
        assert result[0].doc_id == "a"

    def test_llm_model_filter(self) -> None:
        docs = [
            _doc(doc_id="a", llm_model="gemini-2.5-flash"),
            _doc(doc_id="b", llm_model="groq-llama"),
        ]
        result = faceted_search(docs, llm_model="groq-llama")
        assert len(result) == 1
        assert result[0].doc_id == "b"

    def test_prompt_version(self) -> None:
        docs = [
            _doc(doc_id="v1", prompt_version="v1.0"),
            _doc(doc_id="v2", prompt_version="v2.0"),
        ]
        result = faceted_search(docs, prompt_version="v2.0")
        assert len(result) == 1
        assert result[0].doc_id == "v2"

    def test_combined_facets(self) -> None:
        docs = [
            _doc(uf="SP", relev=8, tipo=TipoAto.PROJETO_LEI, doc_id="a"),
            _doc(uf="SP", relev=8, tipo=TipoAto.NOTICIA, doc_id="b"),
            _doc(uf="RJ", relev=8, tipo=TipoAto.PROJETO_LEI, doc_id="c"),
        ]
        result = faceted_search(docs, uf="SP", tipo="projeto_lei", relevancia_min=7)
        assert len(result) == 1
        assert result[0].doc_id == "a"

    def test_query_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="Query"):
            faceted_search([], term="x" * (MAX_QUERY_LENGTH + 1))


@pytest.mark.unit
class TestBoolean:
    def test_implicit_and(self) -> None:
        docs = [
            _doc(titulo="ITCMD em SP progressivo", doc_id="a"),
            _doc(titulo="ITCMD em RJ progressivo", doc_id="b"),
            _doc(titulo="Decreto algo", doc_id="c"),
        ]
        # AND implícito: todos os tokens
        result = boolean_search(docs, "itcmd sp")
        assert any(d.doc_id == "a" for d in result)
        assert all(d.doc_id != "c" for d in result)

    def test_or_explicit(self) -> None:
        docs = [
            _doc(titulo="Apenas ITCMD", doc_id="a"),
            _doc(titulo="Apenas holding", doc_id="b"),
            _doc(titulo="Nada", doc_id="c"),
        ]
        result = boolean_search(docs, "itcmd or holding")
        ids = {d.doc_id for d in result}
        assert "a" in ids and "b" in ids
        assert "c" not in ids

    def test_not_explicit(self) -> None:
        docs = [
            _doc(titulo="ITCMD veto", doc_id="a"),
            _doc(titulo="ITCMD sancao", doc_id="b"),
        ]
        result = boolean_search(docs, "itcmd not veto")
        ids = {d.doc_id for d in result}
        assert "b" in ids
        assert "a" not in ids


@pytest.mark.unit
class TestFuzzy:
    def test_typo_detected(self) -> None:
        docs = [_doc(titulo="ITCMD progressivo SP", doc_id="a")]
        # query com typo
        result = fuzzy_search(docs, "itcmd progressivo sp", threshold=0.5)
        assert len(result) == 1

    def test_threshold_filtra(self) -> None:
        docs = [_doc(titulo="texto totalmente diferente", doc_id="a")]
        result = fuzzy_search(docs, "completamente outro", threshold=0.9)
        assert len(result) == 0


@pytest.mark.unit
class TestHighlight:
    def test_match_case_insensitive(self) -> None:
        result = highlight_term("Lei sobre ITCMD", "itcmd")
        assert "**ITCMD**" in result

    def test_term_vazio(self) -> None:
        assert highlight_term("texto", "") == "texto"


@pytest.mark.unit
class TestMoreLikeThis:
    def test_excluir_o_proprio(self) -> None:
        target = _doc(titulo="Lei ITCMD progressivo SP", doc_id="target")
        docs = [
            target,
            _doc(titulo="Lei ITCMD progressivo SP detalhado", doc_id="similar"),
            _doc(titulo="Decreto ICMS", doc_id="diff"),
        ]
        result = more_like_this(target, docs, threshold=0.3)
        ids = {d.doc_id for d, _ in result}
        assert "target" not in ids
        assert "similar" in ids


@pytest.mark.unit
class TestRegexSearch:
    def test_match_basico(self) -> None:
        docs = [
            _doc(titulo="Lei nº 1234/2026", doc_id="a"),
            _doc(titulo="Decreto sem numero", doc_id="b"),
        ]
        result = regex_search(docs, r"\d+/\d{4}")
        ids = {d.doc_id for d in result}
        assert "a" in ids
        assert "b" not in ids

    def test_regex_invalida(self) -> None:
        with pytest.raises(ValueError, match="Regex"):
            regex_search([], "[invalid(")
