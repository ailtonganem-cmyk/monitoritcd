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

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = current + line + "\n" if current else line + "\n"
        if len(candidate.encode("utf-8")) > max_bytes:
            if current:
                chunks.append(current.rstrip("\n"))
                current = line + "\n"
            else:
                # linha sozinha excede o limite — faz hard split por bytes
                encoded = line.encode("utf-8")
                while len(encoded) > max_bytes:
                    chunks.append(encoded[:max_bytes].decode("utf-8", errors="ignore"))
                    encoded = encoded[max_bytes:]
                current = encoded.decode("utf-8", errors="ignore") + "\n"
        else:
            current = candidate

    if current:
        chunks.append(current.rstrip("\n"))

    return chunks
