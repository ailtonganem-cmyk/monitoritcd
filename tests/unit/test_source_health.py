"""Testes de source_health e source_validators (Categoria 12 IDEAS.md)."""

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
from monitoritcd.source_health import (
    false_positive_rate_per_source,
    health_score,
    items_per_month_per_source,
    revision_calendar,
    should_auto_disable,
    should_auto_reactivate,
    source_volume_summary,
)
from monitoritcd.source_validators import lint_all, lint_source

NOW = datetime.now(UTC)


def _doc(
    *,
    source_id: str = "src",
    age_days: int = 0,
    relev: int = 7,
    with_llm: bool = True,
    uf: str = "SP",
) -> Documento:
    raw = RawItem(
        source_id=source_id,
        titulo_raw="t",
        url="https://x.gov.br/",
        fetched_at=NOW - timedelta(days=age_days),
        data_publicacao=NOW - timedelta(days=age_days),
        content_hash="a" * 64,
    )
    src = Source(
        id=source_id,
        uf=uf,
        nome="x",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = (
        LLMResult(
            classified_at=NOW,
            llm_model="x",
            llm_prompt_version="v1",
            tipo=TipoAto.PROJETO_LEI,
            relevancia=relev,
            severity_tier=SeverityTier.NORMAL,
            resumo="r",
        )
        if with_llm
        else None
    )
    return Documento(
        owner_id="o",
        doc_id=f"d_{source_id}_{age_days}_{relev}",
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED if with_llm else StatusDocumento.PENDING,
    )


@pytest.mark.unit
class TestHealthScore:
    def test_sem_docs(self) -> None:
        score = health_score([], "src")
        assert score["items_count"] == 0
        assert score["success_rate"] == 0

    def test_classified_rate(self) -> None:
        docs = [
            _doc(source_id="s1", with_llm=True),
            _doc(source_id="s1", with_llm=True),
            _doc(source_id="s1", with_llm=False),
        ]
        score = health_score(docs, "s1")
        # 2 de 3 classified
        assert score["success_rate"] == pytest.approx(2 / 3, abs=0.01)

    def test_freshness(self) -> None:
        docs = [_doc(source_id="s1", age_days=10)]
        score = health_score(docs, "s1")
        assert 9 <= score["freshness_days"] <= 11

    def test_freshness_com_data_naive(self) -> None:
        """data_publicacao sem tzinfo é normalizada para UTC antes do cálculo."""
        raw = RawItem(
            source_id="s1",
            titulo_raw="t",
            url="https://x.gov.br/",
            fetched_at=NOW - timedelta(days=3),
            data_publicacao=(NOW - timedelta(days=3)).replace(tzinfo=None),
            content_hash="a" * 64,
        )
        src = Source(
            id="s1",
            uf="SP",
            nome="x",
            tipo=TipoFonte.ASSEMBLEIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        doc = Documento(
            owner_id="o",
            doc_id="naive-1",
            source=src,
            original=raw,
            llm=None,
            status=StatusDocumento.PENDING,
        )
        score = health_score([doc], "s1")
        assert 2 <= score["freshness_days"] <= 4


@pytest.mark.unit
class TestItemsPerMonth:
    def test_buckets(self) -> None:
        docs = [_doc(age_days=5), _doc(age_days=5), _doc(age_days=60)]
        result = items_per_month_per_source(docs)
        # Tudo na mesma source ('src'); 2 buckets
        assert "src" in result
        assert len(result["src"]) >= 2


@pytest.mark.unit
class TestFalsePositiveRate:
    def test_taxa_de_descarte(self) -> None:
        docs = [
            _doc(source_id="s1", relev=3),  # descartado
            _doc(source_id="s1", relev=8),
            _doc(source_id="s1", relev=2),  # descartado
        ]
        result = false_positive_rate_per_source(docs)
        # 2/3 ≈ 0.667
        assert result["s1"]["rate"] == pytest.approx(0.667, abs=0.01)

    def test_ignora_docs_sem_llm(self) -> None:
        """Docs ainda não classificados (llm=None) são pulados via `continue`."""
        docs = [
            _doc(source_id="s1", relev=3, with_llm=False),
            _doc(source_id="s1", relev=8, with_llm=True),
        ]
        result = false_positive_rate_per_source(docs)
        assert result["s1"]["total"] == 1


@pytest.mark.unit
class TestAutoDisable:
    def test_n_falhas_seguidas(self) -> None:
        # 5 últimas todas False (sucesso=False)
        history = [True, True, False, False, False, False, False]
        assert should_auto_disable(history, threshold=5) is True

    def test_intercalado_nao_dispara(self) -> None:
        history = [False, True, False, True, False]
        assert should_auto_disable(history, threshold=3) is False

    def test_historico_curto(self) -> None:
        assert should_auto_disable([False], threshold=5) is False


@pytest.mark.unit
class TestAutoReactivate:
    def test_n_sucessos_seguidos(self) -> None:
        history = [False, False, True, True, True]
        assert should_auto_reactivate(history, threshold=3) is True

    def test_falha_recente(self) -> None:
        history = [True, True, False]
        assert should_auto_reactivate(history, threshold=3) is False

    def test_historico_curto(self) -> None:
        assert should_auto_reactivate([True], threshold=3) is False


@pytest.mark.unit
class TestRevisionCalendar:
    def test_fontes_estagnadas(self) -> None:
        docs = [
            _doc(source_id="ativa", age_days=5),
            _doc(source_id="estagnada", age_days=60),
        ]
        result = revision_calendar(docs, review_period_days=30)
        ids = {sid for sid, _ in result}
        assert "estagnada" in ids
        assert "ativa" not in ids

    def test_fetched_at_naive_e_doc_mais_antigo_nao_sobrescreve(self) -> None:
        """Cobre normalização de fetched_at naive e o ramo em que um doc mais
        antigo (processado depois) não sobrescreve `last_seen` da fonte."""
        src = Source(
            id="s1",
            uf="SP",
            nome="x",
            tipo=TipoFonte.ASSEMBLEIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )

        def _raw(age_days: int, *, naive: bool) -> RawItem:
            fetched = NOW - timedelta(days=age_days)
            if naive:
                fetched = fetched.replace(tzinfo=None)
            return RawItem(
                source_id="s1",
                titulo_raw="t",
                url="https://x.gov.br/",
                fetched_at=fetched,
                content_hash="a" * 64,
            )

        doc_recente = Documento(
            owner_id="o",
            doc_id="s1-recente",
            source=src,
            original=_raw(5, naive=True),
            llm=None,
            status=StatusDocumento.PENDING,
        )
        doc_antigo = Documento(
            owner_id="o",
            doc_id="s1-antigo",
            source=src,
            original=_raw(60, naive=False),
            llm=None,
            status=StatusDocumento.PENDING,
        )
        # Doc mais recente processado primeiro; doc mais antigo depois não deve
        # sobrescrever last_seen (exercita o ramo falso do `or` em revision_calendar).
        result = revision_calendar([doc_recente, doc_antigo], review_period_days=30)
        ids = {sid for sid, _ in result}
        assert "s1" not in ids


@pytest.mark.unit
class TestSourceVolume:
    def test_count_por_source(self) -> None:
        docs = [
            _doc(source_id="a"),
            _doc(source_id="a"),
            _doc(source_id="b"),
        ]
        result = source_volume_summary(docs)
        assert result["a"] == 2
        assert result["b"] == 1


@pytest.mark.unit
class TestLintSource:
    def test_lint_ok(self) -> None:
        src = Source(
            id="alesp",
            uf="SP",
            nome="ALESP",
            tipo=TipoFonte.ASSEMBLEIA,
            parser=Parser.GENERIC_HTML,
            url="https://www.al.sp.gov.br/",
            keywords_required=["ITCMD"],
        )
        warnings = lint_source(src)
        # Tudo ok, esperado vazio
        assert warnings == []

    def test_federal_uf_errado(self) -> None:
        src = Source(
            id="stf-noticias",
            uf="SP",  # errado, deveria ser _federal
            nome="STF",
            tipo=TipoFonte.JURISPRUDENCIA,
            parser=Parser.GENERIC_RSS,
            url="https://stf.jus.br/",
            keywords_required=["ITCMD"],
        )
        warnings = lint_source(src)
        assert any("federal" in w.lower() for w in warnings)

    def test_keywords_sem_itcmd(self) -> None:
        src = Source(
            id="x",
            uf="SP",
            nome="x",
            tipo=TipoFonte.NOTICIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.com/",
            keywords_required=["outro"],
        )
        warnings = lint_source(src)
        assert any("ITCMD" in w for w in warnings)

    def test_lint_all_batch(self) -> None:
        s1 = Source(
            id="ok",
            uf="SP",
            nome="x",
            tipo=TipoFonte.ASSEMBLEIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
            keywords_required=["ITCMD"],
        )
        s2 = Source(
            id="bad",
            uf="SP",
            nome="x",
            tipo=TipoFonte.NOTICIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.com/",
            keywords_required=["nada"],
        )
        result = lint_all([s1, s2])
        assert "bad" in result
        assert "ok" not in result
