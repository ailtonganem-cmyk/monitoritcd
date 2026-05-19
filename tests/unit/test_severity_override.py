"""Testes do `effective_severity` — override de tier por configuração da fonte.

Regra implementada: fontes com `keywords_bypass=True` (ex: doe-mg coletando via
menção a SEFAZ) rebaixam NORMAL→BAIXA. Outros tiers e fontes ficam intactos.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from monitoritcd.core.models import LLMResult, Parser, SeverityTier, Source, TipoAto, TipoFonte
from monitoritcd.notifiers.severity import effective_severity

NOW = datetime.now(UTC)


def _source(*, keywords_bypass: bool = False, org_mentions: list[str] | None = None) -> Source:
    return Source(
        id="src-test",
        uf="MG",
        nome="Teste",
        tipo=TipoFonte.DOE,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
        keywords_bypass=keywords_bypass,
        org_mentions=org_mentions,
    )


def _llm(tier: SeverityTier, *, relevancia: int = 7) -> LLMResult:
    return LLMResult(
        classified_at=NOW,
        llm_model="test",
        llm_prompt_version="v1.0",
        tipo=TipoAto.PORTARIA,
        relevancia=relevancia,
        severity_tier=tier,
        resumo="resumo de teste",
    )


@pytest.mark.unit
class TestEffectiveSeverityNoOverride:
    """Fontes sem `keywords_bypass`: a tier do LLM passa intacta."""

    @pytest.mark.parametrize(
        "tier",
        [
            SeverityTier.CRITICO,
            SeverityTier.ALTA,
            SeverityTier.NORMAL,
            SeverityTier.BAIXA,
            SeverityTier.DESCARTADO,
        ],
    )
    def test_no_bypass_passes_tier_unchanged(self, tier: SeverityTier) -> None:
        src = _source(keywords_bypass=False)
        assert effective_severity(src, _llm(tier)) == tier


@pytest.mark.unit
class TestEffectiveSeverityWithBypass:
    """Fontes com `keywords_bypass=True`: rebaixa NORMAL→BAIXA, outros tiers intactos."""

    def test_bypass_rebaixa_normal_para_baixa(self) -> None:
        src = _source(keywords_bypass=True, org_mentions=["SEFAZ"])
        assert effective_severity(src, _llm(SeverityTier.NORMAL)) == SeverityTier.BAIXA

    def test_bypass_mantem_critico(self) -> None:
        src = _source(keywords_bypass=True, org_mentions=["SEFAZ"])
        assert effective_severity(src, _llm(SeverityTier.CRITICO)) == SeverityTier.CRITICO

    def test_bypass_mantem_alta(self) -> None:
        src = _source(keywords_bypass=True, org_mentions=["SEFAZ"])
        assert effective_severity(src, _llm(SeverityTier.ALTA)) == SeverityTier.ALTA

    def test_bypass_mantem_baixa(self) -> None:
        src = _source(keywords_bypass=True, org_mentions=["SEFAZ"])
        assert effective_severity(src, _llm(SeverityTier.BAIXA)) == SeverityTier.BAIXA

    def test_bypass_mantem_descartado(self) -> None:
        src = _source(keywords_bypass=True, org_mentions=["SEFAZ"])
        assert effective_severity(src, _llm(SeverityTier.DESCARTADO)) == SeverityTier.DESCARTADO


@pytest.mark.unit
class TestEffectiveSeverityIsPure:
    """`effective_severity` é função pura — não muta argumentos."""

    def test_does_not_mutate_llm_result(self) -> None:
        src = _source(keywords_bypass=True, org_mentions=["SEFAZ"])
        original = _llm(SeverityTier.NORMAL)
        _ = effective_severity(src, original)
        # LLMResult é frozen; mas confirma que a tier original não mudou.
        assert original.severity_tier == SeverityTier.NORMAL
