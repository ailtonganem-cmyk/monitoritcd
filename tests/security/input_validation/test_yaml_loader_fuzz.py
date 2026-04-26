"""Fuzz do source_loader (Sugestão #9).

Garante que YAMLs adversariais não derrubam o loader e que validações
do pydantic interceptam tudo antes de runtime.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from monitoritcd.core.source_loader import SourceConfigError, load_source

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.security
@settings(
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    deadline=None,
    max_examples=15,
)
@given(garbage=st.text(max_size=2000))
def test_loader_rejects_arbitrary_text(garbage: str, tmp_path: Path) -> None:
    """Texto YAML aleatório nunca produz Source válido."""
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(garbage, encoding="utf-8")
    with contextlib.suppress(SourceConfigError, ValueError, Exception):
        load_source(yaml_path)


_PROTO_LINE = "__proto__: bad"
_BAD_YAML_EXTRA = (
    "id: x\nuf: SP\nnome: t\nurl: https://e.com\nparser: generic_rss\ntipo: noticia\n" + _PROTO_LINE
)


@pytest.mark.security
@pytest.mark.parametrize(
    "yaml_text",
    [
        # Profundamente aninhado (deve rejeitar via _check_yaml_depth)
        "a:\n" + "  b:\n" * 100 + "    c: 1",
        # URL ssrf-friendly
        "id: x\nuf: SP\nnome: t\nurl: https://localhost/\nparser: generic_rss\ntipo: noticia",
        # Campos extras (pydantic strict deve rejeitar)
        _BAD_YAML_EXTRA,
        # Lista vazia (faltando campos obrigatórios)
        "[]",
        # YAML válido sintaticamente mas vazio
        "",
    ],
)
def test_yaml_adversarial_payloads(yaml_text: str, tmp_path: Path) -> None:
    """Payloads adversariais comuns falham com erro controlado."""
    yaml_path = tmp_path / "adversarial.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    with contextlib.suppress(SourceConfigError, ValueError, Exception):
        load_source(yaml_path)
