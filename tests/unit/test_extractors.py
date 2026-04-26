"""Testes da extração determinística pré-LLM (Sugestão #48)."""

from __future__ import annotations

import pytest

from monitoritcd.filters.extractors import (
    ExtractedMetadata,
    extract_all,
    extract_ato,
    extract_orgao,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected_num", "expected_tipo", "expected_ano"),
    [
        ("Lei nº 1.234/2026 sobre ITCD", "1234/2026", "lei", 2026),
        ("Lei n° 567/2025", "567/2025", "lei", 2025),
        ("LEI 12.345/2024", "12345/2024", "lei", 2024),
        ("Decreto nº 5.678/2025", "5678/2025", "decreto", 2025),
        ("Portaria nº 99/2026", "99/2026", "portaria", 2026),
        ("Instrução Normativa RFB nº 2.123/2026", "2123/2026", "instrucao_normativa", 2026),
        ("IN 2123/2026", "2123/2026", "instrucao_normativa", 2026),
    ],
)
def test_extract_ato_variants(
    text: str, expected_num: str, expected_tipo: str, expected_ano: int
) -> None:
    result = extract_ato(text)
    assert result.numero_ato == expected_num
    assert result.tipo_ato == expected_tipo
    assert result.ano == expected_ano


@pytest.mark.unit
def test_extract_ato_empty() -> None:
    assert extract_ato("") == ExtractedMetadata()
    assert extract_ato("texto sem nada relevante") == ExtractedMetadata()


@pytest.mark.unit
def test_extract_orgao_known() -> None:
    assert extract_orgao("decisão do STF") == "STF"
    assert extract_orgao("STJ se posicionou") == "STJ"


@pytest.mark.unit
def test_extract_orgao_word_boundary() -> None:
    """STF dentro de outra palavra não conta."""
    # "ABCSTF" tem STF como substring mas não como palavra
    result = extract_orgao("ABCSTF não conta")
    # Esperado: não detecta dentro de outra palavra
    assert result is None


@pytest.mark.unit
def test_extract_all_combines() -> None:
    """extract_all combina ato + órgão."""
    result = extract_all("Decreto nº 1234/2026 do STF sobre ITCD")
    assert result.numero_ato == "1234/2026"
    assert result.tipo_ato == "decreto"
    assert result.orgao_emissor == "STF"


@pytest.mark.unit
def test_extract_priority_in_over_lei() -> None:
    """IN tem prioridade sobre Lei (mais específica)."""
    text = "IN 1234/2026 cita Lei 5678/2026"
    result = extract_ato(text)
    # IN é matched primeiro
    assert result.tipo_ato == "instrucao_normativa"


@pytest.mark.unit
def test_normalize_number_via_extract() -> None:
    """Pontos de milhar são removidos do número."""
    result = extract_ato("Lei nº 12.345/2024")
    assert result.numero_ato == "12345/2024"
