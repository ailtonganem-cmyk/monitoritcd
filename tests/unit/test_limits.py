"""Sanity checks dos limites canônicos.

Garantimos que limites são razoáveis e consistentes (ex: MAX_TELEGRAM_MSG = 4096).
Mudanças nestes valores devem ser deliberadas.
"""

from __future__ import annotations

import re

import pytest

from monitoritcd.core import limits


@pytest.mark.unit
class TestLimitConstants:
    def test_telegram_msg_size_matches_official_limit(self) -> None:
        assert limits.MAX_TELEGRAM_MSG_BYTES == 4096

    def test_url_length_matches_de_facto_browser_limit(self) -> None:
        assert limits.MAX_URL_LENGTH == 2048

    def test_relevancia_range_is_zero_to_ten(self) -> None:
        assert limits.RELEVANCIA_MIN == 0
        assert limits.RELEVANCIA_MAX == 10
        assert limits.RELEVANCIA_THRESHOLD_DESCARTADO == 5

    def test_uf_regex_accepts_valid_codes(self) -> None:
        pattern = re.compile(limits.UF_REGEX)
        for uf in ["SP", "RJ", "MG", "RS", "DF", "_federal"]:
            assert pattern.match(uf), f"Should match: {uf}"

    def test_uf_regex_rejects_invalid_codes(self) -> None:
        pattern = re.compile(limits.UF_REGEX)
        for invalid in ["sp", "S", "SPP", "BR", "FEDERAL", "-federal", ""]:
            assert not pattern.match(invalid), f"Should not match: {invalid!r}"

    def test_max_active_ufs_covers_all_brazilian_states(self) -> None:
        assert limits.MAX_ACTIVE_UFS == 27  # 26 estados + DF

    def test_timeouts_are_positive(self) -> None:
        assert limits.HTTP_TIMEOUT_SECONDS > 0
        assert limits.LLM_TIMEOUT_SECONDS > 0
        assert limits.FUNCTION_TIMEOUT_SECONDS > 0
        assert limits.HTTP_TIMEOUT_SECONDS < limits.FUNCTION_TIMEOUT_SECONDS

    def test_byte_limits_are_in_ascending_order(self) -> None:
        assert limits.MAX_REQUEST_BODY_BYTES < limits.MAX_HTML_BYTES
        assert limits.MAX_HTML_BYTES < limits.MAX_PDF_BYTES

    def test_severity_thresholds_are_sequential(self) -> None:
        thresholds = [
            limits.RELEVANCIA_THRESHOLD_DESCARTADO,
            limits.RELEVANCIA_THRESHOLD_BAIXA,
            limits.RELEVANCIA_THRESHOLD_NORMAL,
            limits.RELEVANCIA_THRESHOLD_ALTA,
            limits.RELEVANCIA_THRESHOLD_CRITICO,
        ]
        assert thresholds == sorted(thresholds)
