"""Testes do validador de citações do CC (Sugestão #49)."""

from __future__ import annotations

import pytest

from monitoritcd.filters.citation_validator import (
    is_valid_cc_article,
    validate_cc_citations,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("art_num", "expected"),
    [
        (1, True),  # Parte Geral
        (1639, True),  # Regime de Bens
        (1829, True),  # Sucessões — ordem da vocação hereditária
        (1784, True),  # Início Direito das Sucessões
        (5000, False),  # Fora de range
        (0, False),
        (-1, False),
        (3000, False),
    ],
)
def test_is_valid_cc_article(art_num: int, expected: bool) -> None:
    assert is_valid_cc_article(art_num) is expected


@pytest.mark.unit
def test_validate_no_citations() -> None:
    """Texto sem citações é válido."""
    valid, invalid = validate_cc_citations("texto sem nada")
    assert valid
    assert invalid == []


@pytest.mark.unit
def test_validate_valid_citations() -> None:
    """Citação válida do CC."""
    valid, invalid = validate_cc_citations(
        "art. 1.829 do Código Civil define ordem da vocação hereditária"
    )
    assert valid
    assert invalid == []


@pytest.mark.unit
def test_validate_invalid_citation() -> None:
    """Citação inexistente é flagged."""
    valid, invalid = validate_cc_citations("art. 5000 do Código Civil")
    assert not valid
    assert 5000 in invalid


@pytest.mark.unit
def test_validate_empty_text() -> None:
    valid, invalid = validate_cc_citations("")
    assert valid
    assert invalid == []
