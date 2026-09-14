"""Prepara fonte imutável de Cloud Function (pacote + sources)."""

from __future__ import annotations

import argparse
import shutil
import stat
from pathlib import Path

DEPENDENCIA_LOCAL = "./monitoritcd-src"


def _escrever_dirs(raiz: Path) -> None:
    for diretorio in [raiz, *(item for item in raiz.rglob("*") if item.is_dir())]:
        diretorio.chmod(diretorio.stat().st_mode | stat.S_IWUSR)


def preparar(raiz: Path, nome: str, destino: Path) -> Path:
    """Copia functions/<nome>, pacote src e YAML de sources."""
    if destino.exists():
        raise FileExistsError(f"staging já existe: {destino}")
    shutil.copytree(
        raiz / "functions" / nome,
        destino,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    req = destino / "requirements.txt"
    req.write_text(
        req.read_text(encoding="utf-8").replace(
            "git+https://github.com/ailtonganem-cmyk/monitoritcd.git@main",
            DEPENDENCIA_LOCAL,
        ),
        encoding="utf-8",
    )
    pacote = destino / "monitoritcd-src"
    pacote.mkdir()
    for arquivo in ("pyproject.toml", "README.md"):
        shutil.copy2(raiz / arquivo, pacote / arquivo)
    shutil.copytree(
        raiz / "src",
        pacote / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    cron_auth = pacote / "src" / "monitoritcd" / "security" / "cron_auth.py"
    if nome == "monitor_cron" and not cron_auth.is_file():
        raise FileNotFoundError(f"pacote incompleto: falta {cron_auth}")
    shutil.copytree(
        raiz / "sources",
        destino / "sources",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    _escrever_dirs(destino)
    return destino


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fn", required=True, choices=("monitor_cron", "painel_api"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    destino = preparar(raiz, args.fn, args.output.resolve())
    print(f"Fonte {args.fn} em {destino}")


if __name__ == "__main__":
    main()
