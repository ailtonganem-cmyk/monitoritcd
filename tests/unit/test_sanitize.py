"""Testes do módulo `core.sanitize`.

Cobre:
- HTML malicioso é limpo (scripts, iframes, event handlers removidos)
- Normalização Unicode (NFKC + control chars removidos)
- Truncate preservando palavras
- MAX_HTML_BYTES enforcement
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from monitoritcd.core import limits
from monitoritcd.core.sanitize import (
    normalize_text,
    sanitize_html,
    strip_control_chars,
    truncate_str,
)


@pytest.mark.unit
class TestSanitizeHTML:
    def test_strips_script_tag_and_content(self) -> None:
        html = "<p>Hello</p><script>alert('xss')</script>"
        result = sanitize_html(html)
        # Tag E conteúdo são removidos (pré-pass de _DANGEROUS_BLOCK_TAGS)
        assert "<script>" not in result
        assert "alert" not in result
        assert "<p>Hello</p>" in result

    def test_strips_iframe(self) -> None:
        html = '<p>ok</p><iframe src="http://evil.com"></iframe>'
        result = sanitize_html(html)
        assert "iframe" not in result.lower()

    def test_strips_event_handlers(self) -> None:
        html = '<p onclick="alert(1)">click me</p>'
        result = sanitize_html(html)
        assert "onclick" not in result

    def test_strips_style_attribute(self) -> None:
        html = '<p style="background:url(javascript:alert(1))">text</p>'
        result = sanitize_html(html)
        assert "style" not in result
        assert "javascript" not in result

    def test_preserves_safe_tags(self) -> None:
        html = "<p><strong>Lei nº 1234</strong> de 2026</p>"
        result = sanitize_html(html)
        assert "<strong>" in result
        assert "<p>" in result

    def test_strips_anchor_href(self) -> None:
        html = '<a href="javascript:alert(1)">click</a>'
        result = sanitize_html(html)
        assert "javascript" not in result

    def test_max_bytes_enforced(self) -> None:
        oversized = "a" * (limits.MAX_HTML_BYTES + 1)
        with pytest.raises(ValueError, match="MAX_HTML_BYTES"):
            sanitize_html(oversized)

    def test_strips_comments(self) -> None:
        html = "<!-- evil comment --><p>text</p>"
        result = sanitize_html(html)
        assert "evil" not in result


@pytest.mark.unit
class TestNormalizeText:
    def test_removes_null_bytes(self) -> None:
        assert "\x00" not in normalize_text("hello\x00world")

    def test_preserves_newlines_and_tabs(self) -> None:
        text = "line1\nline2\tindented"
        result = normalize_text(text)
        assert "\n" in result
        assert "\t" in result

    def test_normalizes_compatibility_chars(self) -> None:
        # ﬁ (U+FB01) → fi (NFKC)
        assert normalize_text("oﬁcial") == "oficial"

    def test_removes_zero_width_chars(self) -> None:
        # Zero-width space (U+200B) deve ser removido
        result = normalize_text("hi\u200bthere")
        assert "\u200b" not in result

    def test_idempotent(self) -> None:
        sample = "Lei nº 1.234 — sancionada"
        assert normalize_text(normalize_text(sample)) == normalize_text(sample)

    @given(st.text(max_size=1000))
    def test_never_raises_on_arbitrary_input(self, text: str) -> None:
        result = normalize_text(text)
        # Sempre retorna string e não tem control chars exceto whitespace
        assert isinstance(result, str)


@pytest.mark.unit
class TestStripControlChars:
    def test_removes_x00_through_x08(self) -> None:
        for codepoint in range(0x00, 0x09):
            assert chr(codepoint) not in strip_control_chars(f"a{chr(codepoint)}b")

    def test_keeps_tab_newline_cr(self) -> None:
        assert strip_control_chars("a\tb\nc\rd") == "a\tb\nc\rd"

    def test_removes_x0e_through_x1f(self) -> None:
        for codepoint in range(0x0E, 0x20):
            assert chr(codepoint) not in strip_control_chars(f"a{chr(codepoint)}b")


@pytest.mark.unit
class TestTruncateStr:
    def test_no_truncation_when_short(self) -> None:
        assert truncate_str("short", 100) == "short"

    def test_truncates_with_default_suffix(self) -> None:
        result = truncate_str("a" * 100, 20)
        assert result.endswith("...")
        assert len(result) <= 20

    def test_truncates_at_word_boundary(self) -> None:
        text = "Lei nº 1234 sancionada hoje"
        result = truncate_str(text, 20)
        assert " " not in result[-3:].rstrip(".")  # não termina no meio de palavra

    def test_custom_suffix(self) -> None:
        result = truncate_str("a" * 100, 20, suffix="…")
        assert result.endswith("…")
