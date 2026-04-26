"""Detecção de tentativas de injection (#338 IDEAS.md).

Não substitui validação pydantic/regex (essa é a defesa primária).
Esta camada é detection-only — sinaliza tentativas para audit log.

Suporta:
- SQL injection (UNION/SELECT/--/etc.)
- NoSQL injection (Mongo $-operators, JSON expressions)
- XSS (script tags, javascript:, on*= handlers)
- Prompt injection (instruções para ignorar diretrizes)
- Path traversal (../)
- Command injection (`;`, `|`, `&&`, backticks)

Princípios canônicos:
- Princípio 1: backend não confia em entrada; este é um sinalizador adicional
- Princípio 2: cap em texto avaliado (10KB)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

MAX_INPUT_BYTES: Final[int] = 10_000

# SQL
RE_SQL: Final[re.Pattern[str]] = re.compile(
    r"\b(union\s+select|drop\s+table|insert\s+into|delete\s+from|update\s+set|--\s|\/\*|\*\/|exec\s*\()",
    re.IGNORECASE,
)

# NoSQL
RE_NOSQL: Final[re.Pattern[str]] = re.compile(
    r"\$(eq|ne|gt|lt|gte|lte|in|nin|or|and|not|where|exists|regex)\b",
)

# XSS
RE_XSS: Final[re.Pattern[str]] = re.compile(
    r"<\s*script|javascript:|on(load|click|error|mouseover|focus)\s*=|<\s*iframe|<\s*svg.*on",
    re.IGNORECASE,
)

# Prompt injection (heurística)
RE_PROMPT_INJECTION: Final[re.Pattern[str]] = re.compile(
    r"(ignore\s+(previous|prior|all)\s+instructions|disregard\s+the\s+above"
    r"|system\s*[:=]\s*you\s+are|<\|im_start\|>|act\s+as\s+(a\s+)?system)",
    re.IGNORECASE,
)

# Path traversal
RE_PATH_TRAVERSAL: Final[re.Pattern[str]] = re.compile(
    r"(\.\./|\.\.\\|/etc/passwd|c:\\\\windows|%2e%2e%2f)",
    re.IGNORECASE,
)

# Command injection
RE_CMD_INJECTION: Final[re.Pattern[str]] = re.compile(
    r"(`[^`]+`|\$\(.+?\)|;\s*(rm|cat|ls|wget|curl|bash)\b|\|\s*(rm|cat|nc)\b)",
)

# SSRF (URLs internas)
RE_SSRF: Final[re.Pattern[str]] = re.compile(
    r"(localhost|127\.0\.0\.1|169\.254\.169\.254|metadata\.|::1)",
    re.IGNORECASE,
)


def _bounded(text: str) -> str:
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        text = text[: MAX_INPUT_BYTES // 2]
    return unicodedata.normalize("NFKC", text)


def detect_injection_attempts(text: str) -> dict[str, bool]:
    """Retorna dict de tipos de injection detectados.

    Returns:
        Dict com chaves: sql, nosql, xss, prompt_injection, path_traversal,
        command_injection, ssrf. True se padrão detectado.
    """
    text = _bounded(text)
    return {
        "sql": bool(RE_SQL.search(text)),
        "nosql": bool(RE_NOSQL.search(text)),
        "xss": bool(RE_XSS.search(text)),
        "prompt_injection": bool(RE_PROMPT_INJECTION.search(text)),
        "path_traversal": bool(RE_PATH_TRAVERSAL.search(text)),
        "command_injection": bool(RE_CMD_INJECTION.search(text)),
        "ssrf": bool(RE_SSRF.search(text)),
    }


def has_any_injection(text: str) -> bool:
    """True se qualquer padrão de injection foi detectado."""
    return any(detect_injection_attempts(text).values())


def detected_types(text: str) -> list[str]:
    """Lista tipos de injection detectados (vazia se nenhum)."""
    detected = detect_injection_attempts(text)
    return sorted(k for k, v in detected.items() if v)


__all__ = [
    "MAX_INPUT_BYTES",
    "detect_injection_attempts",
    "detected_types",
    "has_any_injection",
]
