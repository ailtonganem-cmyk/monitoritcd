"""Testes de circuit breaker e keyword matcher (Sugestões #45, #47)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from monitoritcd.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    KeywordMatcher,
)

# ── Circuit Breaker ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_circuit_starts_closed() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state("src1") == CircuitState.CLOSED


@pytest.mark.unit
def test_circuit_opens_after_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure("src1")
    assert cb.state("src1") == CircuitState.OPEN
    with pytest.raises(CircuitBreakerError):
        cb.check("src1")


@pytest.mark.unit
def test_success_resets_circuit() -> None:
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure("src1")
    cb.record_failure("src1")
    cb.record_success("src1")
    # Não abre
    cb.record_failure("src1")
    cb.record_failure("src1")
    assert cb.state("src1") == CircuitState.CLOSED


@pytest.mark.unit
def test_circuit_transitions_to_half_open_after_cooldown() -> None:
    cb = CircuitBreaker(failure_threshold=2, cooldown=timedelta(minutes=10))
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    cb.record_failure("src1", now=t0)
    cb.record_failure("src1", now=t0)
    # Logo após: OPEN
    assert cb.state("src1", now=t0 + timedelta(minutes=5)) == CircuitState.OPEN
    # Após cooldown: HALF_OPEN
    assert cb.state("src1", now=t0 + timedelta(minutes=11)) == CircuitState.HALF_OPEN


@pytest.mark.unit
def test_circuit_isolated_per_key() -> None:
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("src1")
    cb.record_failure("src1")
    assert cb.state("src1") == CircuitState.OPEN
    assert cb.state("src2") == CircuitState.CLOSED


@pytest.mark.unit
def test_circuit_reset() -> None:
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("src1")
    cb.record_failure("src1")
    assert cb.state("src1") == CircuitState.OPEN
    cb.reset("src1")
    assert cb.state("src1") == CircuitState.CLOSED


@pytest.mark.unit
def test_record_failure_uses_now_default() -> None:
    """record_failure usa datetime.now(UTC) quando now=None."""
    cb = CircuitBreaker(failure_threshold=1)
    # Sem `now` explícito
    cb.record_failure("src1")
    assert cb.state("src1") == CircuitState.OPEN


# ── Keyword Matcher ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_keyword_matcher_basic() -> None:
    m = KeywordMatcher(["ITCD", "ITCMD"])
    matched, found = m.find_in("Lei sobre ITCD aprovada")
    assert matched
    assert "itcd" in found


@pytest.mark.unit
def test_keyword_matcher_no_match() -> None:
    m = KeywordMatcher(["ITCD"])
    matched, found = m.find_in("nada relevante aqui")
    assert not matched
    assert found == []


@pytest.mark.unit
def test_keyword_matcher_case_insensitive() -> None:
    m = KeywordMatcher(["ITCD"])
    matched, _ = m.find_in("itcd em minúsculas")
    assert matched


@pytest.mark.unit
def test_keyword_matcher_case_sensitive() -> None:
    m = KeywordMatcher(["ITCD"], case_sensitive=True)
    matched, _ = m.find_in("itcd em minúsculas")
    assert not matched


@pytest.mark.unit
def test_keyword_matcher_dedup() -> None:
    m = KeywordMatcher(["ITCD"])
    _, found = m.find_in("ITCD ITCD ITCD várias vezes")
    assert found.count("itcd") == 1


@pytest.mark.unit
def test_keyword_matcher_multiple() -> None:
    m = KeywordMatcher(["ITCD", "alíquota", "herança"])
    matched, found = m.find_in("ITCD com alíquota nova")
    assert matched
    assert len(found) == 2


@pytest.mark.unit
def test_keyword_matcher_empty_inputs() -> None:
    m = KeywordMatcher([])
    matched, found = m.find_in("texto")
    assert not matched
    assert found == []

    m2 = KeywordMatcher(["ITCD"])
    matched, found = m2.find_in("")
    assert not matched
    assert found == []


@pytest.mark.unit
def test_keyword_matcher_with_empty_string_keyword() -> None:
    """Strings vazias na lista são ignoradas (não causam match em qualquer texto)."""
    m = KeywordMatcher(["ITCD", "", "alíquota"])
    matched, found = m.find_in("alíquota nova")
    assert matched
    assert "alíquota" in found
    assert "" not in found


@pytest.mark.unit
def test_keyword_matcher_uses_correct_path() -> None:
    """A propriedade using_aho_corasick reflete disponibilidade."""
    from monitoritcd.resilience.keyword_matcher import AHO_CORASICK_AVAILABLE  # noqa: PLC0415

    m = KeywordMatcher(["ITCD"])
    assert m.using_aho_corasick == AHO_CORASICK_AVAILABLE


@pytest.mark.unit
def test_keyword_matcher_fallback_path() -> None:
    """Forçar fallback simulando indisponibilidade do AC."""
    from monitoritcd.resilience import keyword_matcher as kw_module  # noqa: PLC0415

    m = KeywordMatcher(["ITCD", "alíquota"])
    # Forçar fallback removendo o automaton
    m._automaton = None
    matched, found = m.find_in("Lei sobre ITCD com alíquota nova")
    assert matched
    assert set(found) == {"itcd", "alíquota"}
    # AHO_CORASICK_AVAILABLE é constante de módulo
    assert isinstance(kw_module.AHO_CORASICK_AVAILABLE, bool)
