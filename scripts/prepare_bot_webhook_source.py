"""Prepara a fonte imutável da Cloud Function ``bot_webhook``.

O pacote ``monitoritcd`` é copiado do checkout já validado para o diretório de
staging. Assim, o Cloud Build não resolve uma referência móvel do Git durante o
deploy.
"""

from __future__ import annotations

import argparse
import re
import shutil
import stat
from pathlib import Path

DEPENDENCIA_MOVEL = "git+https://github.com/ailtonganem-cmyk/monitoritcd.git@main"
DEPENDENCIA_LOCAL = "./monitoritcd-src"
PADRAO_SHA = re.compile(r"[0-9a-f]{40}")


def _habilitar_escrita_em_diretorios(raiz: Path) -> None:
    """Garante que o builder possa criar metadados somente no staging."""
    diretorios = [raiz, *(item for item in raiz.rglob("*") if item.is_dir())]
    for diretorio in diretorios:
        diretorio.chmod(diretorio.stat().st_mode | stat.S_IWUSR)


def preparar_fonte(raiz: Path, destino: Path, sha: str) -> Path:
    """Copia a Function e o pacote local, recusando entrada ambígua ou móvel."""
    if PADRAO_SHA.fullmatch(sha) is None:
        raise ValueError("O SHA candidato deve ter exatamente 40 caracteres hexadecimais.")
    if destino.exists():
        raise FileExistsError(f"O diretório de staging já existe: {destino}")

    fonte_function = raiz / "functions" / "bot_webhook"
    shutil.copytree(
        fonte_function,
        destino,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    _habilitar_escrita_em_diretorios(destino)

    requirements = destino / "requirements.txt"
    conteudo = requirements.read_text(encoding="utf-8")
    if conteudo.count(DEPENDENCIA_MOVEL) != 1:
        raise ValueError("requirements.txt deve conter uma única dependência móvel conhecida.")
    requirements.write_text(
        conteudo.replace(DEPENDENCIA_MOVEL, DEPENDENCIA_LOCAL),
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
    _habilitar_escrita_em_diretorios(pacote)

    if "@main" in requirements.read_text(encoding="utf-8"):
        raise ValueError("A fonte preparada ainda contém referência Git móvel.")

    (destino / "CANDIDATE_SHA").write_text(f"{sha}\n", encoding="utf-8")
    return destino


def main() -> None:
    """Executa o staging a partir da raiz canônica do repositório."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    raiz = Path(__file__).resolve().parents[1]
    preparar_fonte(raiz, args.output.resolve(), args.sha)
    print(f"Fonte bot_webhook preparada para o SHA {args.sha}: {args.output}")


if __name__ == "__main__":
    main()
