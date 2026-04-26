"""Testes do módulo analytics (Categoria 7 IDEAS.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from monitoritcd.analytics import (
    WINDOW_7D_DAYS,
    WINDOW_30D_DAYS,
    actuality_score_per_uf,
    aliquotas_por_uf,
    consolidated_report,
    gap_analysis,
    keyword_frequency,
    maturity_score_per_uf,
    seasonality_by_month,
    sefaz_proactivity_per_uf,
    top_sources_by_relevance,
    top_ufs_by_volume,
    total_valores_monetarios_count,
    trending_topics,
)
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

NOW = datetime.now(UTC)


def _doc(
    *,
    uf: str = "SP",
    age_days: int = 0,
    relev: int = 7,
    tipo: TipoAto = TipoAto.PROJETO_LEI,
    tipo_fonte: TipoFonte = TipoFonte.ASSEMBLEIA,
    tags: list[str] | None = None,
    metadados: dict[str, str] | None = None,
    source_id: str = "src",
) -> Documento:
    raw = RawItem(
        source_id=source_id,
        titulo_raw="t",
        url="https://x.gov.br/",
        fetched_at=NOW,
        data_publicacao=NOW - timedelta(days=age_days),
        content_hash="a" * 64,
    )
    src = Source(
        id=source_id,
        uf=uf,
        nome="x",
        tipo=tipo_fonte,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = LLMResult(
        classified_at=NOW,
        llm_model="x",
        llm_prompt_version="v1",
        tipo=tipo,
        relevancia=relev,
        severity_tier=SeverityTier.NORMAL,
        resumo="r",
        tags=tags or [],
        metadados_extraidos=metadados or {},
    )
    return Documento(
        owner_id="o",
        doc_id=f"d_{source_id}_{uf}_{age_days}_{relev}",
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )


@pytest.mark.unit
class TestTrending:
    def test_trending_7d_filtra_por_janela(self) -> None:
        docs = [
            _doc(tags=["aliquota"], age_days=2),
            _doc(tags=["aliquota"], age_days=10),  # fora da janela 7d
            _doc(tags=["holding"], age_days=1),
        ]
        result = trending_topics(docs, days=WINDOW_7D_DAYS)
        # Em 7d: aliquota=1, holding=1
        keys = [k for k, _ in result]
        assert "aliquota" in keys
        assert "holding" in keys

    def test_trending_30d_inclui_mais(self) -> None:
        docs = [
            _doc(tags=["aliquota"], age_days=2),
            _doc(tags=["aliquota"], age_days=20),
        ]
        result = trending_topics(docs, days=WINDOW_30D_DAYS)
        # aliquota deve ter count = 2
        d = dict(result)
        assert d["aliquota"] == 2

    def test_trending_inclui_temas_especificos(self) -> None:
        docs = [
            _doc(tags=[], metadados={"temas_especificos": "holding_familiar,testamento"}),
        ]
        result = trending_topics(docs, days=WINDOW_7D_DAYS)
        keys = [k for k, _ in result]
        assert "holding_familiar" in keys
        assert "testamento" in keys


@pytest.mark.unit
class TestTopSources:
    def test_filtra_min_docs(self) -> None:
        docs = [
            _doc(source_id="src_a", relev=10),  # só 1 doc; filtrado se min_docs=3
            _doc(source_id="src_b", relev=8),
            _doc(source_id="src_b", relev=8),
            _doc(source_id="src_b", relev=8),
        ]
        result = top_sources_by_relevance(docs, min_docs=3)
        # Apenas src_b qualifica
        assert len(result) == 1
        assert result[0][0] == "src_b"

    def test_ordena_por_relevancia(self) -> None:
        docs = [
            _doc(source_id="low", relev=3),
            _doc(source_id="low", relev=3),
            _doc(source_id="low", relev=3),
            _doc(source_id="hi", relev=9),
            _doc(source_id="hi", relev=9),
            _doc(source_id="hi", relev=9),
        ]
        result = top_sources_by_relevance(docs, min_docs=2)
        # hi deve vir antes de low
        assert result[0][0] == "hi"


@pytest.mark.unit
class TestTopUFs:
    def test_count_por_uf(self) -> None:
        docs = [_doc(uf="SP"), _doc(uf="SP"), _doc(uf="RJ")]
        result = top_ufs_by_volume(docs)
        d = dict(result)
        assert d["SP"] == 2
        assert d["RJ"] == 1


@pytest.mark.unit
class TestGap:
    def test_uf_sem_novidades(self) -> None:
        docs = [_doc(uf="SP", age_days=2)]
        gaps = gap_analysis(docs, active_ufs=["SP", "RJ", "MG"], days=14)
        assert "RJ" in gaps
        assert "MG" in gaps
        assert "SP" not in gaps


@pytest.mark.unit
class TestAliquotas:
    def test_dedup_por_uf(self) -> None:
        docs = [
            _doc(uf="SP", metadados={"aliquotas": "4%,8%"}),
            _doc(uf="SP", metadados={"aliquotas": "4%,8%"}),
            _doc(uf="RJ", metadados={"aliquotas": "4%-8%"}),
        ]
        result = aliquotas_por_uf(docs)
        # SP tem 4%, 8% (dedup); RJ tem range
        assert "4%" in result["SP"]
        assert "8%" in result["SP"]
        assert "4%-8%" in result["RJ"]


@pytest.mark.unit
class TestValores:
    def test_count_docs_com_valores(self) -> None:
        docs = [
            _doc(metadados={"valores_monetarios": "R$ 100"}),
            _doc(),
        ]
        assert total_valores_monetarios_count(docs) == 1


@pytest.mark.unit
class TestKeywords:
    def test_frequencia_global(self) -> None:
        docs = [_doc(tags=["a", "b"]), _doc(tags=["a"])]
        freq = dict(keyword_frequency(docs))
        assert freq["a"] == 2
        assert freq["b"] == 1


@pytest.mark.unit
class TestMaturity:
    def test_score_em_0_1(self) -> None:
        docs = [_doc(uf="SP", relev=8)]
        scores = maturity_score_per_uf(docs)
        assert "SP" in scores
        assert 0 <= scores["SP"] <= 1

    def test_vazio(self) -> None:
        assert maturity_score_per_uf([]) == {}


@pytest.mark.unit
class TestSefazProactivity:
    def test_conta_in_portaria(self) -> None:
        docs = [
            _doc(
                uf="SP",
                tipo_fonte=TipoFonte.SEFAZ,
                tipo=TipoAto.INSTRUCAO_NORMATIVA,
                age_days=10,
            ),
            _doc(
                uf="SP",
                tipo_fonte=TipoFonte.SEFAZ,
                tipo=TipoAto.PORTARIA,
                age_days=20,
            ),
            _doc(uf="SP", tipo_fonte=TipoFonte.NOTICIA, tipo=TipoAto.NOTICIA),
        ]
        result = sefaz_proactivity_per_uf(docs)
        assert result.get("SP") == 2


@pytest.mark.unit
class TestActuality:
    def test_idade_media(self) -> None:
        docs = [_doc(uf="SP", age_days=10), _doc(uf="SP", age_days=20)]
        result = actuality_score_per_uf(docs)
        assert "SP" in result
        # ~15 dias de média (timedelta exato pode variar)
        assert 14 < result["SP"] < 16


@pytest.mark.unit
class TestSeasonality:
    def test_buckets_por_mes(self) -> None:
        # 2 docs em mês X, 1 em mês Y
        docs = [
            _doc(age_days=5),
            _doc(age_days=5),
            _doc(age_days=60),
        ]
        result = seasonality_by_month(docs)
        # Pelo menos 2 buckets
        assert len(result) >= 2


@pytest.mark.unit
class TestConsolidated:
    def test_estrutura_completa(self) -> None:
        docs = [_doc(uf="SP", tags=["a"], metadados={"aliquotas": "4%"})]
        report = consolidated_report(docs, active_ufs=["SP", "RJ"])
        assert "generated_at" in report
        assert report["total_docs"] == 1
        assert "trending_7d" in report
        assert "top_ufs" in report
        assert "RJ" in report["gap_analysis"]
        assert "SP" in report["aliquotas_por_uf"]
