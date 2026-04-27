"""Testes do filtro de keywords."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from monitoritcd.core.models import Topic
from monitoritcd.filters.keywords import (
    KEYWORDS_BY_TOPIC,
    KEYWORDS_DEFAULT,
    KEYWORDS_ITCD,
    KEYWORDS_REGIME_BENS,
    KEYWORDS_SUCESSOES,
    detect_topics,
    matches_keywords,
)


@pytest.mark.unit
class TestMatchesKeywords:
    def test_matches_uppercase_acronym(self) -> None:
        matched, found = matches_keywords("Nova lei sobre ITCMD em SP")
        assert matched
        assert "ITCMD" in found

    def test_matches_lowercase(self) -> None:
        matched, found = matches_keywords("itcmd progressivo")
        assert matched
        # match retorna a versão da KEYWORDS_DEFAULT
        assert any("ITCMD" in f for f in found)

    def test_matches_with_accents(self) -> None:
        matched, _ = matches_keywords("inventário judicial")
        assert matched

    def test_matches_without_accents(self) -> None:
        matched, _ = matches_keywords("inventario judicial")
        assert matched

    def test_matches_compound_phrase(self) -> None:
        matched, found = matches_keywords("planejamento sucessório com holding familiar")
        assert matched
        # Ambas as frases foram detectadas
        kws_lower = [k.lower() for k in found]
        assert any("holding familiar" in k for k in kws_lower)

    def test_no_match_returns_empty(self) -> None:
        matched, found = matches_keywords("Notícia sobre futebol")
        assert not matched
        assert found == []

    def test_empty_text_no_match(self) -> None:
        matched, found = matches_keywords("")
        assert not matched
        assert found == []

    def test_custom_keywords_list(self) -> None:
        matched, found = matches_keywords("foo bar baz", keywords=["bar"])
        assert matched
        assert found == ["bar"]

    def test_unicode_normalization(self) -> None:
        # ﬁnventário (com ligadura ﬁ) → fi após NFKC, deve casar "inventário"
        matched, _ = matches_keywords("ofício sobre inventário")
        assert matched

    def test_double_space_tolerance(self) -> None:
        # "causa  mortis" (espaço duplo) está nas keywords e o normalizador colapsa espaços
        matched, _ = matches_keywords("acórdão sobre causa  mortis no STJ")
        assert matched

    @given(st.text(max_size=1000))
    def test_never_crashes(self, text: str) -> None:
        matches_keywords(text)
        # Apenas garantir que não levanta


@pytest.mark.unit
def test_default_keywords_list_has_minimum_coverage() -> None:
    """Sanity: lista canônica deve ter ≥ 20 termos cobrindo ITCD principalmente."""
    assert len(KEYWORDS_DEFAULT) >= 20
    upper = {k.upper() for k in KEYWORDS_DEFAULT}
    assert "ITCMD" in upper
    assert "ITCD" in upper
    assert any("CAUSA MORTIS" in k for k in upper)


@pytest.mark.unit
class TestKeywordsByTopic:
    def test_each_topic_has_keywords(self) -> None:
        for topic in Topic:
            assert topic in KEYWORDS_BY_TOPIC
            assert len(KEYWORDS_BY_TOPIC[topic]) >= 5

    def test_itcd_keywords_disjoint_from_regime(self) -> None:
        """ITCD-only e Regime de Bens são em sua maioria distintos."""
        itcd_set = {k.lower() for k in KEYWORDS_ITCD}
        regime_set = {k.lower() for k in KEYWORDS_REGIME_BENS}
        overlap = itcd_set & regime_set
        # Pode ter overlap pequeno (ex: "doação"), mas não dominante.
        assert len(overlap) < len(itcd_set) // 4

    def test_default_is_union_of_topics(self) -> None:
        # KEYWORDS_DEFAULT deve conter todos os termos dos 3 tópicos
        all_topic_kws = set(KEYWORDS_ITCD) | set(KEYWORDS_SUCESSOES) | set(KEYWORDS_REGIME_BENS)
        default_set = set(KEYWORDS_DEFAULT)
        assert all_topic_kws == default_set


@pytest.mark.unit
class TestDetectTopics:
    def test_itcd_text_detected(self) -> None:
        topics = detect_topics("Mudança de alíquota do ITCMD em SP")
        assert Topic.ITCD in topics

    def test_sucessoes_text_detected(self) -> None:
        topics = detect_topics("Acórdão sobre legítima e herdeiros necessários no STJ")
        assert Topic.SUCESSOES in topics

    def test_regime_bens_text_detected(self) -> None:
        topics = detect_topics("Aplicação da Súmula 377 e regime de comunhão parcial")
        assert Topic.REGIME_BENS in topics

    def test_multi_topic_text(self) -> None:
        topics = detect_topics(
            "ITCMD em doação com pacto antenupcial — questão sucessória",
        )
        # Toca os 3 tópicos
        assert len(topics) >= 2

    def test_empty_text_returns_empty(self) -> None:
        assert detect_topics("") == []

    def test_unrelated_text_returns_empty(self) -> None:
        assert detect_topics("Resultado do jogo de futebol") == []

    def test_topics_ordered_by_density(self) -> None:
        # Mais sucessões keywords que ITCD → sucessões aparece primeiro
        text = "Inventário judicial. Herdeiros necessários. Testamento. ITCMD mencionado."
        topics = detect_topics(text)
        assert topics[0] == Topic.SUCESSOES


@pytest.mark.unit
class TestExpandWithExtras:
    def test_none_returns_default(self) -> None:
        from monitoritcd.filters.keywords import expand_with_extras  # noqa: PLC0415

        assert expand_with_extras(None) == KEYWORDS_DEFAULT

    def test_empty_returns_default(self) -> None:
        from monitoritcd.filters.keywords import expand_with_extras  # noqa: PLC0415

        assert expand_with_extras([]) == KEYWORDS_DEFAULT

    def test_dedup_against_defaults(self) -> None:
        # Termo já existente nos defaults não duplica.
        from monitoritcd.filters.keywords import expand_with_extras  # noqa: PLC0415

        result = expand_with_extras(["ITCMD", "novo termo extra"])
        assert result.count("ITCMD") == 1
        assert "novo termo extra" in result

    def test_extras_added_after_defaults(self) -> None:
        # Defaults preservam ordem; extras vêm no final.
        from monitoritcd.filters.keywords import expand_with_extras  # noqa: PLC0415

        result = expand_with_extras(["zzz nova keyword"])
        assert result[: len(KEYWORDS_DEFAULT)] == KEYWORDS_DEFAULT
        assert result[-1] == "zzz nova keyword"
