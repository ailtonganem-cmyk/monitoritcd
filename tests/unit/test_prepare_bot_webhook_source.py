"""Regressões do empacotamento imutável da Function ``bot_webhook``."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.prepare_bot_webhook_source import DEPENDENCIA_LOCAL, preparar_fonte

RAIZ = Path(__file__).resolve().parents[2]
SHA = "a" * 40


def test_preparar_fonte_incorpora_pacote_do_checkout(tmp_path: Path) -> None:
    destino = tmp_path / "bot-webhook"

    preparar_fonte(RAIZ, destino, SHA)

    requirements = (destino / "requirements.txt").read_text(encoding="utf-8")
    assert DEPENDENCIA_LOCAL in requirements
    assert "@main" not in requirements
    assert (destino / "monitoritcd-src" / "pyproject.toml").is_file()
    assert (destino / "monitoritcd-src" / "src" / "monitoritcd" / "__init__.py").is_file()
    assert not list(destino.rglob("__pycache__"))
    assert not list(destino.rglob("*.egg-info"))
    assert (destino / "CANDIDATE_SHA").read_text(encoding="utf-8") == f"{SHA}\n"


@pytest.mark.parametrize("sha", ["main", "a" * 39, "A" * 40, "g" * 40])
def test_preparar_fonte_recusa_sha_invalido(tmp_path: Path, sha: str) -> None:
    with pytest.raises(ValueError, match="40 caracteres"):
        preparar_fonte(RAIZ, tmp_path / "bot-webhook", sha)


def test_preparar_fonte_recusa_sobrescrever_staging(tmp_path: Path) -> None:
    destino = tmp_path / "bot-webhook"
    destino.mkdir()

    with pytest.raises(FileExistsError, match="já existe"):
        preparar_fonte(RAIZ, destino, SHA)
