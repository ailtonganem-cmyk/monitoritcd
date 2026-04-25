"""Structlog processor que redige tokens conhecidos antes de logar.

Princípio canônico 3 (CLAUDE.md): secrets nunca expostos em logs.
Este processor é a **última linha de defesa** — se um secret escapou em algum
ponto, ainda é redigido antes de chegar a stdout/arquivo.

Uso:
    import structlog
    from monitoritcd.security.log_redactor import redact_sensitive

    structlog.configure(
        processors=[
            redact_sensitive,  # ANTES dos formatters
            structlog.processors.JSONRenderer(),
        ]
    )
"""

from __future__ import annotations

import re
from typing import Any, Final

# Padrões que devem **sempre** ser redigidos em logs.
# Mantenha em sincronia com `scripts/check_secret_literals.py`.
REDACT_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"sk_live_[0-9A-Za-z]{20,}"), "sk_live_***REDACTED***"),
    (re.compile(r"sk_test_[0-9A-Za-z]{20,}"), "sk_test_***REDACTED***"),
    (re.compile(r"pk_live_[0-9A-Za-z]{20,}"), "pk_live_***REDACTED***"),
    (re.compile(r"whsec_[0-9A-Za-z]{20,}"), "whsec_***REDACTED***"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "AIza***REDACTED***"),
    (re.compile(r"ya29\.[0-9A-Za-z_\-]+"), "ya29.***REDACTED***"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"), "xox*-***REDACTED***"),
    (re.compile(r"ghp_[0-9A-Za-z]{30,}"), "ghp_***REDACTED***"),
    (re.compile(r"gho_[0-9A-Za-z]{30,}"), "gho_***REDACTED***"),
    (re.compile(r"ghu_[0-9A-Za-z]{30,}"), "ghu_***REDACTED***"),
    (re.compile(r"ghs_[0-9A-Za-z]{30,}"), "ghs_***REDACTED***"),
    (re.compile(r"github_pat_[0-9A-Za-z_]{50,}"), "github_pat_***REDACTED***"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "***REDACTED-AWS-KEY***"),
    (re.compile(r"\b\d{8,12}:[A-Za-z0-9_\-]{30,}\b"), "***REDACTED-TELEGRAM-TOKEN***"),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "***REDACTED-PRIVATE-KEY***",
    ),
    # Bearer tokens em headers
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}"), "Bearer ***REDACTED***"),
]

# Chaves de campo cujo valor é sempre considerado sensível.
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "private_key",
        "service_account",
        "session",
        "cookie",
        "x-api-key",
        "x-auth-token",
    }
)


def _redact_string(value: str) -> str:
    """Aplica todos os REDACT_PATTERNS a uma string."""
    for pattern, replacement in REDACT_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _redact_value(value: Any) -> Any:  # noqa: ANN401
    """Redige recursivamente um valor (string, dict, list)."""
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        return {k: _redact_dict_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _redact_dict_value(key: Any, value: Any) -> Any:  # noqa: ANN401
    """Redige o valor de uma chave dict.

    Se a chave (lowercase) está em SENSITIVE_KEYS, redige o valor inteiro.
    Senão, aplica regex patterns no valor.
    """
    if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
        return "***REDACTED***"
    return _redact_value(value)


def redact_sensitive(
    _logger: Any,  # noqa: ANN401
    _name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor: redige tokens em todos os valores.

    Usa duas estratégias combinadas:
    1. Chaves sensíveis (`password`, `token`, etc.) → valor 100% redigido.
    2. Para outras chaves, valores string passam por regex patterns conhecidos.

    Args:
        _logger: BoundLogger (não usado).
        _name: nome do método (não usado).
        event_dict: dicionário de event do structlog.

    Returns:
        event_dict com valores sensíveis redigidos.
    """
    return {k: _redact_dict_value(k, v) for k, v in event_dict.items()}
