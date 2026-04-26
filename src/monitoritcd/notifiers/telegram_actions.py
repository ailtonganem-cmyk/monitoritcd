"""Construção de inline keyboards e callback data para o bot Telegram.

Cobre IDEAS.md Categoria 4: botões de ação rápida (#121), poll/feedback
(#126, #140), expandir resumo (#133), abrir original (#134), tag rápida
(#135).

Princípios canônicos aplicados:
1. **Princípio 1** — `callback_data` é input não confiável (vem do
   cliente Telegram). O handler de callback DEVE re-validar. Aqui
   apenas construímos o payload no formato `prefix:doc_id`.
2. **Princípio 2** — `MAX_CALLBACK_DATA_BYTES = 64` é limite duro do
   Telegram API. Truncamos doc_id se necessário (defensivo).
"""

from __future__ import annotations

from typing import Final

# Limite Telegram API para callback_data (bytes UTF-8)
MAX_CALLBACK_DATA_BYTES: Final[int] = 64

# Prefixos canônicos para callback routing no handler
CB_HELPFUL: Final[str] = "h"
CB_UNHELPFUL: Final[str] = "u"
CB_FAVORITE: Final[str] = "f"
CB_EXPAND: Final[str] = "e"
CB_TAG: Final[str] = "t"
CB_DISMISS: Final[str] = "x"

InlineButton = dict[str, str]
InlineKeyboard = list[list[InlineButton]]


def _truncate_callback(data: str) -> str:
    """Trunca callback_data para caber em 64 bytes UTF-8."""
    encoded = data.encode("utf-8")
    if len(encoded) <= MAX_CALLBACK_DATA_BYTES:
        return data
    # Trunca byte-safe sem cortar caractere multibyte
    return encoded[: MAX_CALLBACK_DATA_BYTES - 1].decode("utf-8", errors="ignore")


def cb(prefix: str, doc_id: str) -> str:
    """Constrói callback_data no formato `prefix:doc_id`.

    Args:
        prefix: prefixo curto (CB_*).
        doc_id: ID do documento (será truncado se necessário).
    """
    raw = f"{prefix}:{doc_id}"
    return _truncate_callback(raw)


def parse_callback(data: str) -> tuple[str, str] | None:
    """Parseia callback_data. Retorna (prefix, doc_id) ou None.

    Validação no handler:
    - prefix em set conhecido
    - doc_id passa por validate_doc_id
    """
    if not data or ":" not in data:
        return None
    prefix, _, doc_id = data.partition(":")
    if not prefix or not doc_id:
        return None
    return prefix, doc_id


def build_item_keyboard(
    doc_id: str,
    *,
    url: str | None = None,
    show_expand: bool = True,
    show_tag: bool = True,
) -> InlineKeyboard:
    """#121, #133, #134, #135, #140 — keyboard padrão por item.

    Linha 1: 👍 útil · 👎 inútil · ⭐ favoritar
    Linha 2: 📖 expandir (se `show_expand`) · 🏷️ tag (se `show_tag`) · 🔗 abrir
    """
    row1: list[InlineButton] = [
        {"text": "👍", "callback_data": cb(CB_HELPFUL, doc_id)},
        {"text": "👎", "callback_data": cb(CB_UNHELPFUL, doc_id)},
        {"text": "⭐", "callback_data": cb(CB_FAVORITE, doc_id)},
    ]
    row2: list[InlineButton] = []
    if show_expand:
        row2.append({"text": "📖 Mais", "callback_data": cb(CB_EXPAND, doc_id)})
    if show_tag:
        row2.append({"text": "🏷️ Tag", "callback_data": cb(CB_TAG, doc_id)})
    if url:
        row2.append({"text": "🔗 Abrir", "url": url})

    keyboard: InlineKeyboard = [row1]
    if row2:
        keyboard.append(row2)
    return keyboard


def build_poll_keyboard(doc_id: str) -> InlineKeyboard:
    """#126 — Poll integrado: "li / não li / arquivar"."""
    return [
        [
            {"text": "✅ Li", "callback_data": cb("li", doc_id)},
            {"text": "👀 Não li", "callback_data": cb("nl", doc_id)},
            {"text": "🗄️ Arquivar", "callback_data": cb("ar", doc_id)},
        ]
    ]


def build_dismiss_keyboard(doc_id: str) -> InlineKeyboard:
    """Keyboard simples só com botão de dispensar (para notificações persistentes)."""
    return [
        [
            {"text": "✖️ Dispensar", "callback_data": cb(CB_DISMISS, doc_id)},
        ]
    ]


__all__ = [
    "CB_DISMISS",
    "CB_EXPAND",
    "CB_FAVORITE",
    "CB_HELPFUL",
    "CB_TAG",
    "CB_UNHELPFUL",
    "MAX_CALLBACK_DATA_BYTES",
    "InlineButton",
    "InlineKeyboard",
    "build_dismiss_keyboard",
    "build_item_keyboard",
    "build_poll_keyboard",
    "cb",
    "parse_callback",
]
