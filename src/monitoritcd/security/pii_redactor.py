"""Mascaramento de PII em logs e mensagens (#337 IDEAS.md).

Remove CPF, CNPJ, e-mail, RG e tokens conhecidos de strings antes de log.
Aplica-se em runtime via structlog processor (registrado em main.py /
log_redactor.py existente).

Princípios canônicos:
- Princípio 1: dados externos podem conter PII inadvertidamente
- Princípio 3: secrets ficam mascarados como "***" mesmo em log debug
"""

from __future__ import annotations

import re
from typing import Final

# CPF: 000.000.000-00 ou 00000000000
RE_CPF: Final[re.Pattern[str]] = re.compile(
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
)

# CNPJ: 00.000.000/0000-00 ou 00000000000000
RE_CNPJ: Final[re.Pattern[str]] = re.compile(
    r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
)

# RG (variável por estado, padrão SP/RJ comum)
RE_RG: Final[re.Pattern[str]] = re.compile(
    r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx]\b",
)

# E-mail
RE_EMAIL: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)

# Telefones BR
RE_TEL: Final[re.Pattern[str]] = re.compile(
    r"\b(?:\+55\s*)?\(?\d{2}\)?\s*9?\d{4}-?\d{4}\b",
)


def redact_cpf(text: str) -> str:
    """Substitui CPFs por `***.***.***-**`."""
    return RE_CPF.sub("***.***.***-**", text)


def redact_cnpj(text: str) -> str:
    """Substitui CNPJs por `**.***.***/****-**`."""
    return RE_CNPJ.sub("**.***.***/****-**", text)


def redact_email(text: str) -> str:
    """Substitui e-mails por `***@***`. Preserva domínio top-level."""
    return RE_EMAIL.sub("***@***", text)


def redact_phone(text: str) -> str:
    """Substitui telefones por `(**)****-****`."""
    return RE_TEL.sub("(**)****-****", text)


def redact_all_pii(text: str) -> str:
    """Aplica todos os redactors em sequência. Idempotente."""
    text = redact_cpf(text)
    text = redact_cnpj(text)
    text = redact_email(text)
    return redact_phone(text)


def has_pii(text: str) -> bool:
    """True se texto contém alguma forma de PII detectável."""
    return any(rgx.search(text) for rgx in (RE_CPF, RE_CNPJ, RE_EMAIL, RE_TEL))


__all__ = [
    "has_pii",
    "redact_all_pii",
    "redact_cnpj",
    "redact_cpf",
    "redact_email",
    "redact_phone",
]
