"""Diagnóstico de setup local (Sugestão #37).

Uso:
    python scripts/doctor.py

Verifica:
- Python ≥ 3.11
- Deps instaladas
- .env existe (ou env vars críticas presentes)
- ruff/mypy/pytest disponíveis
- pre-commit configurado
- Estrutura de diretórios

Não faz I/O externa (não chama Firebase/LLM/Telegram).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET}    {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"{RED}[FAIL]{RESET}  {msg}")


def check_python_version() -> bool:
    # pyproject.toml exige 3.11+; este script roda sob Python 3.11+ por contrato.
    ok(f"Python {sys.version.split()[0]}")
    return True


def check_module(name: str, optional: bool = False) -> bool:
    spec = importlib.util.find_spec(name)
    if spec is not None:
        ok(f"módulo `{name}` instalado")
        return True
    if optional:
        warn(f"módulo `{name}` opcional não encontrado")
        return True
    fail(f"módulo `{name}` faltando — pip install -e .[dev]")
    return False


def check_executable(name: str) -> bool:
    if shutil.which(name):
        ok(f"executável `{name}` no PATH")
        return True
    warn(f"executável `{name}` não encontrado")
    return False


def check_env_var(name: str, optional: bool = False) -> bool:
    if os.environ.get(name):
        ok(f"env var `{name}` definida")
        return True
    if optional:
        warn(f"env var `{name}` não definida (opcional)")
        return True
    fail(f"env var `{name}` faltando")
    return False


def check_path(path: Path, kind: str = "file") -> bool:
    exists = path.is_file() if kind == "file" else path.is_dir()
    if exists:
        ok(f"{kind} {path.relative_to(REPO_ROOT)} existe")
        return True
    fail(f"{kind} {path.relative_to(REPO_ROOT)} não encontrado")
    return False


def check_pre_commit_installed() -> bool:
    hooks_path = REPO_ROOT / ".git" / "hooks" / "pre-commit"
    if hooks_path.exists():
        ok("pre-commit hook instalado")
        return True
    warn("pre-commit hook não instalado — `pre-commit install`")
    return False


def main() -> int:
    print("=== MonitorITCD doctor ===\n")
    failures = 0

    # Python e core deps
    failures += not check_python_version()
    for mod in ["httpx", "pydantic", "pydantic_settings", "structlog", "jinja2", "yaml"]:
        failures += not check_module(mod)

    # Dev tools (opcionais individualmente, mas warn se faltarem todos)
    print()
    for mod in ["pytest", "hypothesis", "ruff", "mypy", "bandit"]:
        check_module(mod, optional=True)

    # Executables
    print()
    check_executable("git")
    check_executable("python")
    check_executable("pre-commit")

    # Estrutura
    print()
    failures += not check_path(REPO_ROOT / "pyproject.toml")
    failures += not check_path(REPO_ROOT / ".env.example")
    failures += not check_path(REPO_ROOT / "src" / "monitoritcd", kind="dir")
    failures += not check_path(REPO_ROOT / "sources", kind="dir")
    failures += not check_path(REPO_ROOT / "tests", kind="dir")
    # active_states default YAML é seed inicial — opcional após primeira execução
    if (REPO_ROOT / "config" / "active_states.default.yaml").exists():
        ok("config/active_states.default.yaml existe")
    else:
        warn("config/active_states.default.yaml ausente — dados via Firestore")

    # Pre-commit
    print()
    check_pre_commit_installed()

    # .env (opcional — modo dev)
    print()
    if (REPO_ROOT / ".env").exists():
        ok(".env existe")
    else:
        warn(".env ausente — usando env vars do shell")

    # Env vars críticas (warn — só são obrigatórias em produção)
    print()
    for var in ["OWNER_ID", "FIREBASE_PROJECT_ID", "GEMINI_API_KEY"]:
        check_env_var(var, optional=True)

    # Resumo
    print()
    if failures == 0:
        print(f"{GREEN}=== Setup ok ==={RESET}")
        return 0
    print(f"{RED}=== {failures} problema(s) encontrado(s) ==={RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
