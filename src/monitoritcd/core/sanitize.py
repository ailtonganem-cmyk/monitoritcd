"""Wrappers de sanitização — defense-in-depth (Seção 7 do CLAUDE.md).

Camadas de sanitização:
- HTML coletado de fontes externas → `sanitize_html`
- Texto bruto antes de passar pro LLM → `normalize_text`
- Texto antes de exibir → `strip_control_chars`

Princípio: cliente é hostil por padrão (Princípio Canônico 1).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

import bleach

from monitoritcd.core import limits

# Tags cujo conteúdo INTEIRO deve ser removido (não só a tag) antes do bleach.
# `<script>alert(1)</script>` precisa virar "" — bleach com strip=True remove
# a tag mas preserva o texto interno; aqui removemos texto + tag.
_DANGEROUS_BLOCK_TAGS: Final[tuple[str, ...]] = (
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "noscript",
    "noembed",
    "applet",
    "frame",
    "frameset",
)
_DANGEROUS_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"<(" + "|".join(_DANGEROUS_BLOCK_TAGS) + r")\b[^>]*>.*?</\1\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_DANGEROUS_SELFCLOSE_RE: Final[re.Pattern[str]] = re.compile(
    r"<(" + "|".join(_DANGEROUS_BLOCK_TAGS) + r")\b[^>]*/?>",
    flags=re.IGNORECASE,
)

# Tags HTML permitidas após sanitização (foco em conteúdo legível, sem scripting/styling).
ALLOWED_TAGS: Final[list[str]] = [
    "p",
    "br",
    "ul",
    "ol",
    "li",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "code",
    "pre",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "hr",
]

# Atributos permitidos (vazio: apenas estrutura, sem href/src/style/onclick/etc.)
ALLOWED_ATTRIBUTES: Final[dict[str, list[str]]] = {}


def sanitize_html(html: str) -> str:
    """Limpa HTML coletado antes de armazenar.

    Remove scripts, styles, event handlers, iframes, etc.
    Preserva estrutura textual básica para resumo legível.

    Args:
        html: HTML cru de uma fonte externa.

    Returns:
        HTML limpo, seguro para armazenar/exibir.

    Raises:
        ValueError: se input excede MAX_HTML_BYTES.
    """
    if len(html.encode("utf-8")) > limits.MAX_HTML_BYTES:
        msg = f"HTML excede MAX_HTML_BYTES ({limits.MAX_HTML_BYTES} bytes)"
        raise ValueError(msg)

    # Pré-pass: remove tags perigosas COM seu conteúdo (script, style, iframe, ...).
    # Bleach.clean(strip=True) sozinho remove a tag mas preserva o texto interno;
    # para essas tags o texto interno é parte do ataque (CSS @import, JS code).
    pre = _DANGEROUS_BLOCK_RE.sub("", html)
    pre = _DANGEROUS_SELFCLOSE_RE.sub("", pre)

    cleaned: str = bleach.clean(
        pre,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
        strip_comments=True,
    )
    return cleaned


def normalize_text(text: str) -> str:
    """Normaliza Unicode (NFKC) e remove control chars.

    Mantém `\\n` e `\\t` mas remove demais control chars (`\\x00-\\x08`, `\\x0e-\\x1f`, etc.)
    que podem ser usados em ataques de homoglyph ou bypass de filtros.

    Args:
        text: texto bruto.

    Returns:
        Texto normalizado, sem control chars exceto whitespace legível.
    """
    text = unicodedata.normalize("NFKC", text)
    return strip_control_chars(text)


def strip_control_chars(text: str) -> str:
    """Remove caracteres de controle exceto `\\n`, `\\t` e `\\r`.

    Categorias Unicode "Cc" (control), "Cf" (format), "Cn" (unassigned),
    "Co" (private use), "Cs" (surrogate) são removidas.
    """
    allowed_whitespace = {"\n", "\t", "\r"}
    return "".join(
        c for c in text if c in allowed_whitespace or not unicodedata.category(c).startswith("C")
    )


def truncate_str(text: str, max_length: int, suffix: str = "...") -> str:
    """Trunca texto preservando palavras quando possível.

    Atenção: este helper é para **renderização** (display), não para validação.
    Inputs **devem ser rejeitados** se excederem limits — não truncados (Princípio 2).
    """
    if len(text) <= max_length:
        return text
    truncated = text[: max_length - len(suffix)]
    last_space = truncated.rfind(" ")
    if last_space > max_length // 2:
        truncated = truncated[:last_space]
    return truncated + suffix
