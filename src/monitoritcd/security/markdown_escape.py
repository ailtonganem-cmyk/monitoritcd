"""Escape de Markdown V2 para Telegram.

Documentação oficial:
https://core.telegram.org/bots/api#markdownv2-style

Chars que **devem** ser escapados quando NÃO são parte de formatação:
`_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!`

Princípio canônico 1 (CLAUDE.md): backend nunca confia no frontend.
Mensagem de bot **sempre** passa por escape antes de enviar — mesmo que o conteúdo
pareça "limpo".
"""

from __future__ import annotations

from typing import Final

# Chars especiais do MarkdownV2 que requerem escape com `\`
MARKDOWN_V2_SPECIAL: Final[str] = r"_*[]()~`>#+-=|{}.!\\"

# Chars que precisam escape DENTRO de blocos de código (apenas `\` e `` ` ``)
CODE_BLOCK_SPECIAL: Final[str] = r"`\\"

# Chars que precisam escape em `pre`/`code` blocks (idem)
PRE_CODE_SPECIAL: Final[str] = r"`\\"


def escape_markdown_v2(text: str) -> str:
    """Escapa todos os chars especiais do MarkdownV2 do Telegram.

    Use SEMPRE antes de enviar conteúdo arbitrário em mensagem MarkdownV2.

    Args:
        text: texto a escapar.

    Returns:
        Texto com chars especiais precedidos de `\\`.

    Example:
        >>> escape_markdown_v2("PL 1234/2026 (SP) - sancionado!")
        'PL 1234/2026 \\(SP\\) \\- sancionado\\!'
    """
    if not text:
        return ""

    result: list[str] = []
    for char in text:
        if char in MARKDOWN_V2_SPECIAL:
            result.append("\\")
        result.append(char)
    return "".join(result)


def escape_code_block(text: str) -> str:
    """Escapa chars dentro de bloco ` ``` ` (backtick triple)."""
    return text.replace("\\", "\\\\").replace("`", "\\`")


def safe_link(text: str, url: str) -> str:
    """Constrói link MarkdownV2 escapando o texto exibido e o URL.

    Args:
        text: texto a exibir no link.
        url: URL de destino.

    Returns:
        String no formato `[texto escapado](url escapado)`.
    """
    escaped_text = escape_markdown_v2(text)
    escaped_url = url.replace("\\", "\\\\").replace(")", "\\)")
    return f"[{escaped_text}]({escaped_url})"


def split_for_telegram(text: str, max_bytes: int = 4096) -> list[str]:
    """Divide texto em chunks ≤ `max_bytes` bytes (UTF-8) preservando linhas.

    Args:
        text: texto possivelmente grande.
        max_bytes: limite por mensagem (default: 4096, limite do Telegram).

    Returns:
        Lista de mensagens, cada uma ≤ max_bytes em UTF-8.
    """
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    def trailing_backslashes(value: str) -> int:
        count = 0
        for char in reversed(value):
            if char != "\\":
                break
            count += 1
        return count

    def split_oversized_line(line: str) -> list[str]:
        """Divide linha longa por bytes sem cortar escape MarkdownV2."""
        parts: list[str] = []
        remaining = line
        while len(remaining.encode("utf-8")) > max_bytes:
            used = 0
            split_at = 0
            for idx, char in enumerate(remaining):
                char_bytes = len(char.encode("utf-8"))
                if used + char_bytes > max_bytes:
                    break
                used += char_bytes
                split_at = idx + 1
            while split_at > 1 and trailing_backslashes(remaining[:split_at]) % 2 == 1:
                split_at -= 1
            if split_at <= 0:
                split_at = 1
            parts.append(remaining[:split_at])
            remaining = remaining[split_at:]
        if remaining:
            parts.append(remaining)
        return parts or [""]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        line_with_newline = line + "\n"
        if len(line_with_newline.encode("utf-8")) > max_bytes:
            if current:
                chunks.append(current.rstrip("\n"))
                current = ""
            parts = split_oversized_line(line)
            chunks.extend(parts[:-1])
            current = parts[-1] + "\n"
            continue

        candidate = current + line_with_newline if current else line_with_newline
        if len(candidate.encode("utf-8")) > max_bytes:
            if current:
                chunks.append(current.rstrip("\n"))
            current = line_with_newline
        else:
            current = candidate

    if current:
        chunks.append(current.rstrip("\n"))

    return chunks
