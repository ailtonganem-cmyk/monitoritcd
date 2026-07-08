"""Testes do módulo watches (Categoria 9 IDEAS.md)."""

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
    Topic,
    Watch,
)
from monitoritcd.watches import (
    SIMILAR_HIGH_THRESHOLD,
    evaluate_watches,
    find_template,
    fuzzy_watches_for_query,
    get_templates,
    is_in_cooldown,
    is_watch_active,
    matches_aliquota_change,
    matches_cluster,
    matches_doc,
    matches_high_relevance,
    matches_modulacao,
    matches_revogacao,
    matches_similar,
    matches_tipo,
)

NOW = datetime.now(UTC)


def _doc(
    *,
    titulo: str = "Lei sobre ITCMD em SP",
    uf: str = "SP",
    relev: int = 7,
    metadados: dict[str, str] | None = None,
    tipo: TipoAto = TipoAto.PROJETO_LEI,
    topics: list[Topic] | None = None,
    cluster_id: str | None = None,
    with_llm: bool = True,
) -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw=titulo,
        url="https://x.gov.br/",
        fetched_at=NOW,
        data_publicacao=NOW,
        content_hash="a" * 64,
    )
    src = Source(
        id="src",
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
            tipo=tipo,
            relevancia=relev,
            severity_tier=SeverityTier.NORMAL,
            resumo="resumo padrao",
            metadados_extraidos=metadados or {},
            topics=topics or [Topic.ITCD],
        )
        if with_llm
        else None
    )
    return Documento(
        owner_id="o",
        doc_id="d1",
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
        cluster_id=cluster_id,
    )


def _watch(
    *,
    pattern: str,
    pattern_type: str = "term",
    uf: str | None = None,
    relevancia_min: int = 5,
    expires_at: datetime | None = None,
    cooldown_hours: int = 0,
    last_triggered: datetime | None = None,
) -> Watch:
    return Watch(
        owner_id="o",
        watch_id="w1",
        pattern=pattern,
        pattern_type=pattern_type,  # type: ignore[arg-type]
        uf=uf,
        relevancia_min=relevancia_min,
        expires_at=expires_at,
        cooldown_hours=cooldown_hours,
        last_triggered=last_triggered,
        created_at=NOW,
    )


@pytest.mark.unit
class TestTemplates:
    def test_lista_nao_vazia(self) -> None:
        templates = get_templates()
        assert len(templates) > 0

    def test_find_existente(self) -> None:
        tpl = find_template("holding_familiar")
        assert tpl is not None
        assert "holding" in tpl["pattern"].lower()

    def test_find_inexistente(self) -> None:
        assert find_template("nonexistent") is None


@pytest.mark.unit
class TestExpiracao:
    def test_watch_sem_expiracao_ativo(self) -> None:
        assert is_watch_active(_watch(pattern="x")) is True

    def test_expirado(self) -> None:
        past = NOW - timedelta(days=1)
        assert is_watch_active(_watch(pattern="x", expires_at=past)) is False

    def test_futuro(self) -> None:
        future = NOW + timedelta(days=7)
        assert is_watch_active(_watch(pattern="x", expires_at=future)) is True

    def test_expires_at_naive_datetime(self) -> None:
        """expires_at sem tzinfo é normalizado para UTC antes da comparação."""
        future_naive = (NOW + timedelta(days=1)).replace(tzinfo=None)
        assert is_watch_active(_watch(pattern="x", expires_at=future_naive)) is True

        past_naive = (NOW - timedelta(days=1)).replace(tzinfo=None)
        assert is_watch_active(_watch(pattern="x", expires_at=past_naive)) is False


@pytest.mark.unit
class TestCooldown:
    def test_sem_cooldown(self) -> None:
        assert is_in_cooldown(_watch(pattern="x")) is False

    def test_em_cooldown(self) -> None:
        recent = NOW - timedelta(hours=1)
        w = _watch(pattern="x", cooldown_hours=24, last_triggered=recent)
        assert is_in_cooldown(w) is True

    def test_cooldown_expirado(self) -> None:
        old = NOW - timedelta(hours=48)
        w = _watch(pattern="x", cooldown_hours=24, last_triggered=old)
        assert is_in_cooldown(w) is False

    def test_last_triggered_naive_datetime(self) -> None:
        """last_triggered sem tzinfo é normalizado para UTC antes da comparação."""
        recent_naive = (NOW - timedelta(hours=1)).replace(tzinfo=None)
        w = _watch(pattern="x", cooldown_hours=24, last_triggered=recent_naive)
        assert is_in_cooldown(w) is True

        old_naive = (NOW - timedelta(hours=48)).replace(tzinfo=None)
        w2 = _watch(pattern="x", cooldown_hours=24, last_triggered=old_naive)
        assert is_in_cooldown(w2) is False


@pytest.mark.unit
class TestMatchesDoc:
    def test_term_match(self) -> None:
        w = _watch(pattern="ITCMD", pattern_type="term")
        assert matches_doc(w, _doc()) is True

    def test_term_no_match(self) -> None:
        w = _watch(pattern="ICMS", pattern_type="term")
        assert matches_doc(w, _doc()) is False

    def test_term_logical_and(self) -> None:
        w = _watch(pattern="itcmd and sp", pattern_type="term")
        assert matches_doc(w, _doc(titulo="ITCMD em SP")) is True

    def test_term_logical_or(self) -> None:
        w = _watch(pattern="itcmd or icms", pattern_type="term")
        assert matches_doc(w, _doc(titulo="Lei sobre ITCMD")) is True

    def test_regex_match(self) -> None:
        w = _watch(pattern=r"\d+/\d{4}", pattern_type="regex")
        assert matches_doc(w, _doc(titulo="Lei nº 1234/2026")) is True

    def test_regex_invalido_nao_match(self) -> None:
        w = _watch(pattern="[invalid(", pattern_type="regex")
        assert matches_doc(w, _doc()) is False

    def test_pl_number_match(self) -> None:
        w = _watch(pattern="1234/2026", pattern_type="pl_number")
        doc = _doc(metadados={"numero_ato": "1234/2026"})
        assert matches_doc(w, doc) is True

    def test_pl_number_no_match(self) -> None:
        w = _watch(pattern="9999/2020", pattern_type="pl_number")
        doc = _doc(metadados={"numero_ato": "1234/2026"})
        assert matches_doc(w, doc) is False

    def test_uf_topic_match(self) -> None:
        w = _watch(pattern="SP:itcd", pattern_type="uf_topic")
        doc = _doc(uf="SP", topics=[Topic.ITCD])
        assert matches_doc(w, doc) is True

    def test_uf_topic_via_metadados(self) -> None:
        w = _watch(pattern="SP:holding_familiar", pattern_type="uf_topic")
        doc = _doc(uf="SP", metadados={"temas_especificos": "holding_familiar,testamento"})
        assert matches_doc(w, doc) is True

    def test_uf_filter_blocks(self) -> None:
        w = _watch(pattern="ITCMD", pattern_type="term", uf="RJ")
        # doc é SP; uf RJ → False
        assert matches_doc(w, _doc(uf="SP")) is False

    def test_relevancia_min_filter(self) -> None:
        w = _watch(pattern="ITCMD", pattern_type="term", relevancia_min=8)
        # doc relev=5 → False
        assert matches_doc(w, _doc(relev=5)) is False
        assert matches_doc(w, _doc(relev=9)) is True

    def test_pattern_type_desconhecido(self) -> None:
        """pattern_type fora dos 4 suportados cai no fallback False."""
        w = _watch(pattern="qualquer", pattern_type="term")
        # Bypassa o Literal via object.__setattr__ pois Watch não é frozen aqui
        object.__setattr__(w, "pattern_type", "outro")
        assert matches_doc(w, _doc()) is False

    def test_term_match_sem_llm(self) -> None:
        """_term_match ignora resumo quando doc.llm é None."""
        w = _watch(pattern="ITCMD", pattern_type="term")
        doc = _doc(titulo="Lei sobre ITCMD em SP", with_llm=False)
        assert matches_doc(w, doc) is True

    def test_uf_topic_sem_dois_pontos(self) -> None:
        w = _watch(pattern="SPitcd", pattern_type="uf_topic")
        assert matches_doc(w, _doc()) is False

    def test_uf_topic_uf_diferente(self) -> None:
        w = _watch(pattern="RJ:itcd", pattern_type="uf_topic")
        assert matches_doc(w, _doc(uf="SP")) is False

    def test_uf_topic_sem_llm(self) -> None:
        w = _watch(pattern="SP:itcd", pattern_type="uf_topic")
        doc = _doc(uf="SP", with_llm=False)
        assert matches_doc(w, doc) is False


@pytest.mark.unit
class TestEspecializados:
    def test_high_relevance(self) -> None:
        assert matches_high_relevance(_doc(relev=9), min_score=8) is True
        assert matches_high_relevance(_doc(relev=5), min_score=8) is False

    def test_aliquota_change(self) -> None:
        doc = _doc(metadados={"aliquotas": "4%,8%"})
        assert matches_aliquota_change(doc) is True
        assert matches_aliquota_change(_doc()) is False

    def test_revogacao(self) -> None:
        doc = _doc(metadados={"revogacoes_citadas": "1234/2020"})
        assert matches_revogacao(doc) is True

    def test_modulacao(self) -> None:
        doc = _doc(metadados={"modulacao_efeitos": "true"})
        assert matches_modulacao(doc) is True

    def test_tipo(self) -> None:
        assert matches_tipo(_doc(tipo=TipoAto.DECRETO), "decreto") is True
        assert matches_tipo(_doc(tipo=TipoAto.NOTICIA), "decreto") is False

    def test_similar_high(self) -> None:
        doc = _doc(titulo="Lei ITCMD progressiva SP 2026")
        assert matches_similar(doc, "Lei ITCMD progressiva SP 2026") is True

    def test_similar_low(self) -> None:
        doc = _doc(titulo="Texto totalmente diferente")
        assert (
            matches_similar(doc, "Lei ITCMD progressiva SP 2026", threshold=SIMILAR_HIGH_THRESHOLD)
            is False
        )

    def test_cluster(self) -> None:
        doc = _doc(cluster_id="abc123")
        assert matches_cluster(doc, "abc123") is True
        assert matches_cluster(doc, "xyz789") is False


@pytest.mark.unit
class TestEvaluateWatches:
    def test_match_basico(self) -> None:
        watches = [_watch(pattern="ITCMD", pattern_type="term")]
        docs = [_doc()]
        result = evaluate_watches(docs, watches)
        assert len(result) == 1

    def test_filtra_expirados(self) -> None:
        past = NOW - timedelta(days=1)
        watches = [_watch(pattern="ITCMD", pattern_type="term", expires_at=past)]
        docs = [_doc()]
        assert evaluate_watches(docs, watches) == []

    def test_filtra_cooldown(self) -> None:
        recent = NOW - timedelta(hours=1)
        watches = [
            _watch(pattern="ITCMD", pattern_type="term", cooldown_hours=24, last_triggered=recent)
        ]
        docs = [_doc()]
        assert evaluate_watches(docs, watches) == []


@pytest.mark.unit
class TestFuzzyWatchesForQuery:
    def test_encontra_similar(self) -> None:
        docs = [_doc(titulo="Lei ITCMD progressiva SP 2026")]
        result = fuzzy_watches_for_query(docs, "Lei ITCMD progressiva SP 2026", threshold=0.8)
        assert len(result) == 1

    def test_sem_match(self) -> None:
        docs = [_doc(titulo="Assunto totalmente não relacionado")]
        result = fuzzy_watches_for_query(docs, "Lei ITCMD progressiva SP 2026")
        assert result == []
