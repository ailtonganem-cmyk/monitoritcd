"""Testes do telegram_actions (inline keyboards e callback parsing).

Cobre IDEAS.md Categoria 4: #121, #126, #133, #134, #135, #140.
"""

from __future__ import annotations

import pytest

from monitoritcd.notifiers.telegram_actions import (
    CB_DISMISS,
    CB_EXPAND,
    CB_FAVORITE,
    CB_HELPFUL,
    CB_TAG,
    CB_UNHELPFUL,
    MAX_CALLBACK_DATA_BYTES,
    build_dismiss_keyboard,
    build_item_keyboard,
    build_poll_keyboard,
    cb,
    parse_callback,
)


@pytest.mark.unit
class TestCallbackData:
    def test_cb_format(self) -> None:
        assert cb(CB_HELPFUL, "doc_123") == "h:doc_123"

    def test_cb_truncates_long_doc_id(self) -> None:
        long_doc = "x" * 200
        result = cb(CB_HELPFUL, long_doc)
        assert len(result.encode("utf-8")) <= MAX_CALLBACK_DATA_BYTES

    def test_cb_handles_unicode(self) -> None:
        # Emoji UTF-8 multibyte
        result = cb(CB_HELPFUL, "🔥" * 30)
        assert len(result.encode("utf-8")) <= MAX_CALLBACK_DATA_BYTES


@pytest.mark.unit
class TestParseCallback:
    def test_parse_valid(self) -> None:
        assert parse_callback("h:doc_123") == ("h", "doc_123")

    def test_parse_empty(self) -> None:
        assert parse_callback("") is None

    def test_parse_no_colon(self) -> None:
        assert parse_callback("invalid") is None

    def test_parse_only_prefix(self) -> None:
        assert parse_callback("h:") is None

    def test_parse_only_doc_id(self) -> None:
        assert parse_callback(":doc_123") is None


@pytest.mark.unit
class TestBuildItemKeyboard:
    def test_full_keyboard(self) -> None:
        kb = build_item_keyboard("doc_1", url="https://example.com/")
        assert len(kb) == 2
        assert len(kb[0]) == 3  # 👍 👎 ⭐
        # Linha 2 tem expand + tag + abrir
        assert any("Mais" in btn["text"] for btn in kb[1])
        assert any("url" in btn for btn in kb[1])

    def test_no_url(self) -> None:
        kb = build_item_keyboard("doc_1", url=None)
        # Sem botão URL
        flat = [btn for row in kb for btn in row]
        assert all("url" not in btn for btn in flat)

    def test_no_expand_no_tag_only_first_row(self) -> None:
        kb = build_item_keyboard("doc_1", show_expand=False, show_tag=False)
        # Apenas 1 linha (👍 👎 ⭐); sem segunda linha
        assert len(kb) == 1


@pytest.mark.unit
class TestBuildPollKeyboard:
    def test_three_options(self) -> None:
        kb = build_poll_keyboard("doc_1")
        assert len(kb) == 1
        assert len(kb[0]) == 3
        texts = [btn["text"] for btn in kb[0]]
        assert "✅ Li" in texts
        assert "👀 Não li" in texts


@pytest.mark.unit
class TestBuildDismissKeyboard:
    def test_single_button(self) -> None:
        kb = build_dismiss_keyboard("doc_1")
        assert kb[0][0]["callback_data"] == f"{CB_DISMISS}:doc_1"


@pytest.mark.unit
class TestPrefixesIntegrity:
    def test_all_prefixes_unique(self) -> None:
        prefixes = {CB_HELPFUL, CB_UNHELPFUL, CB_FAVORITE, CB_EXPAND, CB_TAG, CB_DISMISS}
        assert len(prefixes) == 6
