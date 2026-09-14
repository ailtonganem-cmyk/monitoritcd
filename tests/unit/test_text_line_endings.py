"""Invariante: fontes rastreadas usam LF. Cópia Windows não pode deixar CR."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Binários e artefatos que podem conter byte 0x0D sem ser fim de linha.
_BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".webp",
        ".pdf",
        ".gz",
        ".zip",
        ".whl",
        ".pyc",
        ".so",
        ".exe",
        ".pyd",
        ".dll",
    }
)


def _arquivos_rastreados() -> list[Path]:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git não está no PATH")
    resultado = subprocess.run(  # noqa: S603
        [git, "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    rels = [item.decode() for item in resultado.stdout.split(b"\0") if item]
    return [REPO_ROOT / rel for rel in rels]


def _eh_texto(path: Path) -> bool:
    if path.suffix.lower() in _BINARY_SUFFIXES:
        return False
    try:
        amostra = path.read_bytes()[:8192]
    except OSError:
        return False
    return b"\0" not in amostra


@pytest.mark.unit
def test_arquivos_texto_rastreados_usam_lf() -> None:
    ofensores: list[str] = []
    for path in _arquivos_rastreados():
        if not _eh_texto(path):
            continue
        if b"\r" in path.read_bytes():
            ofensores.append(path.relative_to(REPO_ROOT).as_posix())
    assert ofensores == [], (
        f"{len(ofensores)} arquivo(s) com CR/CRLF (cópia Windows?). Exemplos: {ofensores[:20]}"
    )


@pytest.mark.unit
def test_shebang_rastreado_nao_termina_com_cr() -> None:
    quebrados: list[str] = []
    for path in _arquivos_rastreados():
        if not _eh_texto(path):
            continue
        bruta = path.read_bytes()
        if not bruta.startswith(b"#!"):
            continue
        primeira, _sep, _resto = bruta.partition(b"\n")
        if primeira.endswith(b"\r"):
            quebrados.append(path.relative_to(REPO_ROOT).as_posix())
    assert quebrados == [], f"Shebang com CR quebra execução POSIX: {quebrados}"
