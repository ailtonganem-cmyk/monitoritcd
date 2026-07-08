"""Cobre branches faltantes em `source_validators.py`."""

from __future__ import annotations

import pytest

from monitoritcd.core.models import Parser, Source, TipoFonte, Topic
from monitoritcd.source_validators import lint_all, lint_source


def _make_source(**overrides: object) -> Source:
    base = {
        "id": "test-src",
        "uf": "SP",
        "nome": "Test Source",
        "tipo": TipoFonte.NOTICIA,
        "parser": Parser.GENERIC_RSS,
        "url": "https://example.gov.br/feed",
        "topics": [Topic.ITCD],
        "ativo": True,
        "fragile": False,
    }
    base.update(overrides)
    return Source(**base)  # type: ignore[arg-type]


@pytest.mark.unit
def test_lint_source_clean() -> None:
    """Source válida não gera warnings."""
    s = _make_source(keywords_required=["ITCMD"])
    assert lint_source(s) == []


@pytest.mark.unit
def test_lint_keywords_without_core() -> None:
    """keywords_required sem ITCMD/ITCD/ITD gera warning."""
    s = _make_source(keywords_required=["herança"])
    warnings = lint_source(s)
    assert any("keywords_required sem" in w for w in warnings)


@pytest.mark.unit
def test_lint_federal_with_wrong_uf() -> None:
    """ID começando com 'stf' mas uf != _federal."""
    s = _make_source(id="stf-rss", uf="SP")
    warnings = lint_source(s)
    assert any("Fonte federal" in w for w in warnings)


@pytest.mark.unit
def test_lint_fragile_without_notas() -> None:
    """fragile=True sem notas gera warning."""
    s = _make_source(fragile=True, notas=None)
    warnings = lint_source(s)
    assert any("fragile" in w and "notas" in w for w in warnings)


@pytest.mark.unit
def test_lint_all_filters_clean_sources() -> None:
    """lint_all retorna apenas sources com warnings."""
    clean = _make_source(id="clean", keywords_required=["ITCD"])
    dirty = _make_source(id="dirty", keywords_required=["x"])
    out = lint_all([clean, dirty])
    assert "clean" not in out
    assert "dirty" in out


@pytest.mark.unit
def test_lint_gov_url_sem_https() -> None:
    """URL de domínio .gov.br/.jus.br/.leg.br sem HTTPS gera warning."""
    s = _make_source(url="http://example.gov.br/feed", keywords_required=["ITCD"])
    warnings = lint_source(s)
    assert any("sem HTTPS" in w for w in warnings)


@pytest.mark.unit
def test_lint_topics_vazio() -> None:
    """topics=[] gera warning."""
    s = _make_source(topics=[], keywords_required=["ITCD"])
    warnings = lint_source(s)
    assert any("topics vazio" in w for w in warnings)


@pytest.mark.unit
def test_lint_ativo_sem_geo_restricted_bool() -> None:
    """Fonte ativa com geo_restricted não-bool (bypass de validação) gera warning."""
    s = _make_source(keywords_required=["ITCD"])
    # Princípio 1 garante bool no schema; simula corrupção via model_construct
    # (bypassa validators) para exercitar o guard defensivo de lint_source.
    tampered = s.model_construct(**{**s.model_dump(), "geo_restricted": None})
    warnings = lint_source(tampered)
    assert any("sem geo_restricted" in w for w in warnings)
