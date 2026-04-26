"""Regression tests do prompt LLM.

Sugestão #13: bump em `PROMPT_VERSION` deve forçar revisão consciente.

Estratégia:
- Snapshot do prompt atual + schema esperado.
- Bump de versão → snapshot quebra → dono aprova com `pytest --snapshot-update`.
"""

from __future__ import annotations

import pytest

from monitoritcd.filters.llm_classifier import (
    PROMPT_VERSION,
    SEVERITY_THRESHOLDS,
    SYSTEM_PROMPT,
)


@pytest.mark.unit
def test_prompt_version_format() -> None:
    """Versão do prompt segue formato semver-like (vMAJOR.MINOR)."""
    assert PROMPT_VERSION.startswith("v")
    parts = PROMPT_VERSION[1:].split(".")
    assert len(parts) == 2
    assert all(p.isdigit() for p in parts)


@pytest.mark.unit
def test_system_prompt_has_inegociaveis() -> None:
    """Regras inegociáveis (Seção 5 CLAUDE.md) estão no system prompt."""
    assert "INEGOCIÁVEIS" in SYSTEM_PROMPT
    assert "verbatim" in SYSTEM_PROMPT.lower()
    assert "anonimize" in SYSTEM_PROMPT.lower()


@pytest.mark.unit
def test_system_prompt_has_topics() -> None:
    """Os 3 tópicos canônicos estão presentes."""
    for topic in ("itcd", "sucessoes", "regime_bens"):
        assert topic in SYSTEM_PROMPT.lower()


@pytest.mark.unit
def test_severity_thresholds_monotonic() -> None:
    """Thresholds devem ser monotonicamente decrescentes."""
    thresholds = [t[0] for t in SEVERITY_THRESHOLDS]
    assert thresholds == sorted(thresholds, reverse=True)


@pytest.mark.unit
def test_system_prompt_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    """Snapshot de fingerprint do prompt — bump força aprovação consciente."""
    # Capturar apenas características invariantes — não o texto inteiro
    # (linhas se reorganizam, mas regras inegociáveis devem persistir).
    fingerprint = {
        "version": PROMPT_VERSION,
        "n_lines": SYSTEM_PROMPT.count("\n"),
        "has_topics_section": "topics" in SYSTEM_PROMPT,
        "has_relevancia_scale": "9-10" in SYSTEM_PROMPT,
        "has_pt_br_directive": "PT-BR" in SYSTEM_PROMPT,
        "n_inegociaveis": SYSTEM_PROMPT.count("\n   "),
    }
    assert fingerprint == snapshot
