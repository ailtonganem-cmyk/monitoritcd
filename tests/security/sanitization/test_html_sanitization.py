"""Testes de segurança da sanitização HTML.

Foco: garantir que payloads conhecidos de XSS / injection NÃO passam.
Lista baseada em OWASP XSS Filter Evasion Cheat Sheet.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from monitoritcd.core.sanitize import sanitize_html


@pytest.mark.security
class TestXSSPayloads:
    """Payloads do OWASP XSS Cheat Sheet."""

    @pytest.mark.parametrize(
        "payload",
        [
            "<script>alert('xss')</script>",
            "<scr<script>ipt>alert(1)</script>",
            "<IMG SRC=javascript:alert('XSS')>",
            "<IMG SRC=JaVaScRiPt:alert('XSS')>",
            "<IMG SRC=&#106;&#97;&#118;&#97;&#115;&#99;&#114;&#105;&#112;&#116;:alert('XSS')>",
            "<IMG SRC=\"jav\tascript:alert('XSS');\">",
            "<svg/onload=alert(1)>",
            "<body onload=alert(1)>",
            '<iframe src="javascript:alert(1)"></iframe>',
            "<link rel=stylesheet href=javascript:alert(1)>",
            '<a href="javascript:alert(1)">click</a>',
            '<form action="javascript:alert(1)"><input type=submit></form>',
            '<input type="image" src="javascript:alert(1)">',
            '<object data="javascript:alert(1)">',
            '<embed src="javascript:alert(1)">',
            '<META HTTP-EQUIV="refresh" CONTENT="0;url=javascript:alert(1)">',
            "<style>@import 'javascript:alert(1)';</style>",
            '<div onmouseover="alert(1)">hover</div>',
            "<input autofocus onfocus=alert(1)>",
            "<details open ontoggle=alert(1)>",
        ],
    )
    def test_xss_payload_neutralized(self, payload: str) -> None:
        result = sanitize_html(payload)
        # Verifica que NENHUM ataque conhecido aparece de forma executável
        result_lower = result.lower()
        assert "<script" not in result_lower
        assert "javascript:" not in result_lower
        assert "onerror" not in result_lower
        assert "onload" not in result_lower
        assert "onclick" not in result_lower
        assert "onmouseover" not in result_lower
        assert "onfocus" not in result_lower
        assert "ontoggle" not in result_lower
        assert "<iframe" not in result_lower
        assert "<embed" not in result_lower
        assert "<object" not in result_lower
        assert "<meta" not in result_lower


@pytest.mark.security
class TestEscapeBypassAttempts:
    def test_unicode_obfuscation(self) -> None:
        # `\u003cscript\u003e` é uma forma de tentar bypass
        payload = "\u003cscript\u003ealert(1)\u003c/script\u003e"
        result = sanitize_html(payload)
        assert "<script>" not in result.lower()

    def test_double_encoding(self) -> None:
        payload = "%3Cscript%3Ealert(1)%3C/script%3E"
        # bleach não decodifica URL — deve manter literal
        result = sanitize_html(payload)
        # Não vira tag executável
        assert "<script>" not in result.lower()

    def test_polyglot_payload(self) -> None:
        # Payload que tenta ser válido em múltiplos contextos
        payload = (
            "jaVasCript:/*-/*`/*\\`/*'/*\"/**/(/* */oNcliCk=alert() )//"
            "%0D%0A%0d%0a//</stYle/</titLe/</teXtarEa/</scRipt/--!>"
            "\\x3csVg/<sVg/oNloAd=alert()//>\\x3e"
        )
        result = sanitize_html(payload)
        assert "alert" not in result.lower() or "<script" not in result.lower()
        assert "<svg" not in result.lower()


@pytest.mark.security
class TestPropertyBased:
    @given(st.text(max_size=500))
    def test_no_executable_payload_in_output(self, text: str) -> None:
        result = sanitize_html(text)
        result_lower = result.lower()
        # Output nunca pode ter tags executáveis
        forbidden_substrings = [
            "<script",
            "<iframe",
            "<object",
            "<embed",
            "javascript:",
            "onerror=",
            "onload=",
            "onclick=",
        ]
        for forbidden in forbidden_substrings:
            assert forbidden not in result_lower, f"Vazou {forbidden!r} de input {text!r}"
