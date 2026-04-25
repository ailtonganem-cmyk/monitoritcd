"""Fuzz testing dos parsers de comando do bot.

Princípio canônico 1: backend não confia. Mesmo que o canal Telegram seja
"trusted", entradas devem resistir a:
- payloads grandes
- chars especiais e Unicode
- comandos malformados
"""

from __future__ import annotations

import contextlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from monitoritcd.bot.handlers import parse_command


@pytest.mark.security
class TestParseCommand:
    def test_normal_command(self) -> None:
        cmd = parse_command("/buscar ITCMD SP")
        assert cmd is not None
        assert cmd.name == "buscar"
        assert cmd.args == ["ITCMD", "SP"]

    def test_command_with_botname_suffix(self) -> None:
        # Telegram usa /command@BotName em grupos
        cmd = parse_command("/start@MonitorITCDBot")
        assert cmd is not None
        assert cmd.name == "start"

    def test_no_slash_returns_none(self) -> None:
        assert parse_command("buscar ITCMD") is None

    def test_empty_returns_none(self) -> None:
        assert parse_command("") is None

    def test_only_slash_returns_none(self) -> None:
        cmd = parse_command("/")
        # `/` sozinho parseia como nome vazio — caller decide rejeitar
        assert cmd is not None
        assert cmd.name == ""

    def test_too_long_command_rejected(self) -> None:
        from monitoritcd.core import limits  # noqa: PLC0415

        too_long = "/" + "a" * (limits.MAX_BOT_COMMAND_LENGTH + 1)
        with pytest.raises(ValueError, match="MAX_BOT_COMMAND_LENGTH"):
            parse_command(too_long)

    def test_too_long_arg_rejected(self) -> None:
        from monitoritcd.core import limits  # noqa: PLC0415

        too_long_arg = "a" * (limits.MAX_BOT_ARG_LENGTH + 1)
        with pytest.raises(ValueError, match="MAX_BOT_ARG_LENGTH"):
            parse_command(f"/buscar {too_long_arg}")

    def test_too_many_args_rejected(self) -> None:
        many_args = " ".join([f"a{i}" for i in range(15)])
        with pytest.raises(ValueError, match="argumentos"):
            parse_command(f"/buscar {many_args}")

    def test_uppercase_normalized_to_lower(self) -> None:
        cmd = parse_command("/BUSCAR ITCMD")
        assert cmd is not None
        assert cmd.name == "buscar"

    @given(st.text(max_size=200))
    def test_never_crashes(self, text: str) -> None:
        # Fuzz: para qualquer texto de tamanho razoável,
        # parse_command só pode lançar ValueError ou retornar.
        with contextlib.suppress(ValueError):
            parse_command(text)

    @given(st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_categories=("Cc",))))
    def test_random_command_no_crash(self, name: str) -> None:
        text = "/" + name
        with contextlib.suppress(ValueError):
            parse_command(text)

    def test_unicode_in_args(self) -> None:
        # Caracteres Unicode em argumentos não devem quebrar o parser
        cmd = parse_command("/buscar ITCMD 中文")
        assert cmd is not None
        assert "中文" in cmd.args

    def test_emoji_in_args_safe(self) -> None:
        cmd = parse_command("/buscar 🇧🇷")
        assert cmd is not None
        assert "🇧🇷" in cmd.args
