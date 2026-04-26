"""Lint semântico dos YAMLs em sources/ (Sugestão #38).

Carrega cada YAML via pydantic — pega erros de schema antes de runtime.
Diferença de yamllint: validação de tipos + valores válidos, não só sintaxe.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO_ROOT / "sources"


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from monitoritcd.core.source_loader import (  # noqa: PLC0415
        SourceConfigError,
        load_source,
    )

    files = sorted(SOURCES_DIR.rglob("*.yaml"))
    if not files:
        print(f"Nenhum YAML em {SOURCES_DIR}")
        return 1

    failures: list[tuple[Path, str]] = []
    for f in files:
        try:
            load_source(f)
        except SourceConfigError as e:
            failures.append((f, f"SourceConfigError: {e}"))
        except Exception as e:  # noqa: BLE001
            failures.append((f, f"{type(e).__name__}: {e}"))

    if not failures:
        print(f"OK — {len(files)} YAMLs validados")
        return 0

    print(f"FALHA — {len(failures)}/{len(files)} YAMLs inválidos:")
    for path, err in failures:
        rel = path.relative_to(REPO_ROOT)
        print(f"  {rel}: {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
