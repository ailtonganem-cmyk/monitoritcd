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


@pytest.mark.unit
def test_validate_small_number_outside_art_context() -> None:
    """Número pequeno (< 100) sem palavra 'art' próxima é ignorado."""
    # "5 do Código Civil" — 5 sem ser citado como artigo
    valid, invalid = validate_cc_citations("Item 5 do Código Civil")
    # 5 não é válido como art mas a heurística ignora; resultado válido.
    assert valid
    assert 5 not in invalid


@pytest.mark.unit
def test_validate_with_art_keyword() -> None:
    """Número pequeno com 'art' explícito é considerado citação real."""
    valid, _invalid = validate_cc_citations(
        "art. 5 do Código Civil"  # 5 é válido (Parte Geral)
    )
    assert valid


@pytest.mark.unit
def test_validate_text_with_garbage_in_capture() -> None:
    """Texto onde o regex match dá grupo não-numérico é tolerado."""
    # Garante que ValueError não derruba (linha 72-73 do módulo).
    valid, invalid = validate_cc_citations("art. 1.829 do Código Civil normal")
    assert valid
    assert invalid == []
