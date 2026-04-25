"""Carrega configurações de fontes a partir de YAMLs em `sources/`.

Cada YAML é validado por:
1. `yaml.safe_load` (não permite tags arbitrárias).
2. `validate_url` para `url` (anti-SSRF, Princípio Canônico 1).
3. `Source` pydantic model (input_limits + extra=forbid, Princípios 1+2).

Falhas são propagadas (fail loud) — CI bloqueia merge de YAML inválido.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — usado em runtime (path.read_text, etc.)
from typing import Any

import structlog
import yaml

from monitoritcd.core import limits
from monitoritcd.core.models import Source
from monitoritcd.security.url_validator import validate_url

logger = structlog.get_logger(__name__)


class SourceConfigError(ValueError):
    """YAML de fonte inválido ou não-conforme."""


def _check_yaml_depth(data: Any, max_depth: int, current: int = 0) -> None:  # noqa: ANN401
    """Valida profundidade do YAML (Princípio 2: MAX_DEPTH)."""
    if current > max_depth:
        msg = f"YAML excede MAX_YAML_DEPTH ({max_depth})"
        raise SourceConfigError(msg)
    if isinstance(data, dict):
        for v in data.values():
            _check_yaml_depth(v, max_depth, current + 1)
    elif isinstance(data, list):
        for v in data:
            _check_yaml_depth(v, max_depth, current + 1)


def load_source(yaml_path: Path) -> Source:
    """Carrega um arquivo YAML e valida como `Source`.

    Args:
        yaml_path: caminho absoluto ou relativo ao YAML.

    Returns:
        `Source` pydantic model.

    Raises:
        SourceConfigError: YAML mal-formado, URL não-segura ou schema inválido.
        OSError: arquivo não existe ou sem permissão.
    """
    if not yaml_path.is_file():
        msg = f"YAML de fonte não encontrado: {yaml_path}"
        raise SourceConfigError(msg)

    raw_text = yaml_path.read_text(encoding="utf-8")
    if len(raw_text.encode("utf-8")) > limits.MAX_REQUEST_BODY_BYTES:
        msg = f"YAML excede MAX_REQUEST_BODY_BYTES: {yaml_path}"
        raise SourceConfigError(msg)

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        msg = f"YAML mal-formado em {yaml_path}: {e}"
        raise SourceConfigError(msg) from e

    if not isinstance(data, dict):
        msg = f"YAML em {yaml_path} deve ser um mapping; obtido: {type(data).__name__}"
        raise SourceConfigError(msg)

    _check_yaml_depth(data, limits.MAX_YAML_DEPTH)

    # Anti-SSRF antes do pydantic — mensagem específica
    if "url" in data and isinstance(data["url"], str):
        try:
            validate_url(data["url"])
        except ValueError as e:
            msg = f"URL não-segura em {yaml_path}: {e}"
            raise SourceConfigError(msg) from e

    try:
        return Source(**data)
    except (TypeError, ValueError) as e:
        msg = f"Schema inválido em {yaml_path}: {e}"
        raise SourceConfigError(msg) from e


def load_all_sources(
    sources_dir: Path,
    *,
    ativo_only: bool = False,
) -> list[Source]:
    """Carrega todos os YAMLs em `sources_dir` recursivamente.

    Args:
        sources_dir: diretório raiz (ex: `sources/`).
        ativo_only: se True, filtra apenas fontes com `ativo: true`.

    Returns:
        Lista de Sources, ordenada por id.

    Raises:
        SourceConfigError: se qualquer YAML for inválido (fail loud).
    """
    if not sources_dir.is_dir():
        msg = f"Diretório de fontes não existe: {sources_dir}"
        raise SourceConfigError(msg)

    sources: list[Source] = []
    seen_ids: set[str] = set()

    for yaml_path in sorted(sources_dir.rglob("*.yaml")):
        src = load_source(yaml_path)
        if src.id in seen_ids:
            msg = f"id duplicado de fonte: {src.id} (em {yaml_path})"
            raise SourceConfigError(msg)
        seen_ids.add(src.id)

        if ativo_only and not src.ativo:
            continue
        sources.append(src)

    sources.sort(key=lambda s: s.id)
    return sources
