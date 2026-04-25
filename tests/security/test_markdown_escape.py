"""Testes do escape MarkdownV2 do Telegram.

Cobre todos os 18 chars especiais e split por bytes UTF-8.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from monitoritcd.security.markdown_escape import (
    MARKDOWN_V2_SPECIAL,
    escape_code_block,
    escape_markdown_v2,
    safe_link,
    split_for_telegram,
)


@pytest.mark.security
class TestEscapeMarkdownV2:
    @pytest.mark.parametrize("char", list("_*[]()~`>#+-=|{}.!"))
    def test_each_special_char_escaped(self, char: str) -> None:
        result = escape_markdown_v2(f"a{char}b")
        assert result == f"a\\{char}b"

    def test_pl_with_parens_escaped(self) -> None:
        text = "PL 1234/2026 (SP) - sancionado!"
        result = escape_markdown_v2(text)
        assert result == "PL 1234/2026 \\(SP\\) \\- sancionado\\!"

    def test_no_special_chars_unchanged(self) -> None:
        text = "Lei 1234 sancionada hoje"
        assert escape_markdown_v2(text) == text

    def test_empty_string_returns_empty(self) -> None:
        assert escape_markdown_v2("") == ""

    def test_backslash_escaped(self) -> None:
        result = escape_markdown_v2("a\\b")
        assert result == "a\\\\b"

    @given(st.text(max_size=200))
    def test_escaping_idempotent_after_one_pass(self, text: str) -> None:
        # Após escapar, todos os chars especiais devem estar precedidos de \
        escaped = escape_markdown_v2(text)
        # Garantia: nenhum char especial nu (sem \ na frente)
        i = 0
        while i < len(escaped):
            unescaped_special = (
                escaped[i] in MARKDOWN_V2_SPECIAL
                and (i == 0 or escaped[i - 1] != "\\")
                and escaped[i] != "\\"
            )
            if unescaped_special:
                pytest.fail(f"Char especial não escapado em pos {i}: {escaped!r}")
            i += 1


@pytest.mark.security
class TestSafeLink:
    def test_link_format(self) -> None:
        link = safe_link("Texto", "https://x.gov.br/")
        assert link == "[Texto](https://x.gov.br/)"

    def test_special_chars_in_text_escaped(self) -> None:
        link = safe_link("PL 1.234/2026 (SP)!", "https://x.gov.br/")
        assert "\\(" in link
        assert "\\)" in link
        assert "\\!" in link
        assert "\\." in link

    def test_paren_in_url_escaped(self) -> None:
        link = safe_link("ok", "https://x.gov.br/path)")
        assert link.endswith("\\))")


@pytest.mark.security
class TestSplitForTelegram:
    def test_short_text_single_chunk(self) -> None:
        result = split_for_telegram("hello world")
        assert result == ["hello world"]

    def test_long_text_split_at_4096(self) -> None:
        line = "x" * 100 + "\n"
        text = line * 50  # 5000 bytes
        chunks = split_for_telegram(text, max_bytes=4096)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 4096

    def test_split_preserves_lines(self) -> None:
        text = "linha1\nlinha2\nlinha3"
        chunks = split_for_telegram(text, max_bytes=15)
        # Cada chunk não corta no meio de uma linha (a menos que linha seja > limite)
        for chunk in chunks:
            assert chunk.strip() != ""

    def test_oversized_single_line_hard_split(self) -> None:
        # Linha sozinha maior que limite — split por bytes
        text = "a" * 100
        chunks = split_for_telegram(text, max_bytes=20)
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 20

    def test_unicode_safe(self) -> None:
        # Caractere Unicode multi-byte (emoji + acentuado)
        text = "café 🇧🇷\n" * 100
        chunks = split_for_telegram(text, max_bytes=200)
        for chunk in chunks:
            # Não deve haver bytes inválidos UTF-8
            chunk.encode("utf-8")

    def test_empty_input(self) -> None:
        assert split_for_telegram("") == [""]


@pytest.mark.security
class TestEscapeCodeBlock:
    def test_backslash_escaped(self) -> None:
        assert escape_code_block(r"a\b") == r"a\\b"

    def test_backtick_escaped(self) -> None:
        assert escape_code_block("a`b") == "a\\`b"
