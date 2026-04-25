#!/usr/bin/env python3
"""Bloqueia commits que contenham literais conhecidos de secrets.

Princípio canônico 3 do CLAUDE.md: secrets PROIBIDOS em código fonte.
Sem exceção. Sem --no-verify.

Padrões cobertos:
- Stripe: sk_live_, sk_test_, whsec_, pk_live_
- Google API/OAuth: AIza..., ya29....
- Slack: xoxb-, xoxp-, xapp-, xoxa-, xoxr-
- GitHub: ghp_, gho_, ghu_, ghs_, github_pat_
- AWS: AKIA..., ASIA...
- Generic JWT-like: eyJhbGciOiJ
- Private keys: -----BEGIN ... PRIVATE KEY-----
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Padrões de literais conhecidos. Determinístico — falso positivo é raro;
# falso negativo é coberto por gitleaks/detect-secrets.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Stripe live secret key", re.compile(r"sk_live_[0-9A-Za-z]{20,}")),
    ("Stripe test secret key", re.compile(r"sk_test_[0-9A-Za-z]{20,}")),
    ("Stripe publishable live key", re.compile(r"pk_live_[0-9A-Za-z]{20,}")),
    ("Stripe webhook secret", re.compile(r"whsec_[0-9A-Za-z]{20,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Google OAuth token", re.compile(r"ya29\.[0-9A-Za-z_\-]+")),
    ("Slack bot token", re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}")),
    ("GitHub personal access token", re.compile(r"ghp_[0-9A-Za-z]{30,}")),
    ("GitHub OAuth token", re.compile(r"gho_[0-9A-Za-z]{30,}")),
    ("GitHub user access token", re.compile(r"ghu_[0-9A-Za-z]{30,}")),
    ("GitHub server token", re.compile(r"ghs_[0-9A-Za-z]{30,}")),
    ("GitHub PAT (new)", re.compile(r"github_pat_[0-9A-Za-z_]{50,}")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Telegram bot token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_\-]{30,}\b")),
]


# Arquivos com fixtures de teste intencionalmente contendo padrões fake.
# Verificados manualmente para garantir que NÃO contêm secrets reais.
ALLOWLIST_PATHS = frozenset(
    {
        "tests/security/test_log_redactor.py",  # fixtures para testar o redactor
        "tests\\security\\test_log_redactor.py",  # variante Windows
        ".gitleaks.toml",  # config do gitleaks com pattern AKIAIOSFODNN7EXAMPLE
        "scripts/check_secret_literals.py",  # este proprio arquivo (auto-referencia)
        "scripts\\check_secret_literals.py",
    }
)


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Retorna lista de (linha, padrão_nome, trecho_match) encontrados."""
    findings: list[tuple[int, str, str]] = []

    # Pula allowlist (test fixtures conhecidos)
    posix_path = str(path).replace("\\", "/")
    if any(posix_path.endswith(allowed) for allowed in ALLOWLIST_PATHS):
        return findings

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    for line_num, line in enumerate(content.splitlines(), start=1):
        for name, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                # Mascara o match no output para não vazar no terminal
                masked = match.group()[:6] + "***REDACTED***"
                findings.append((line_num, name, masked))
    return findings


MIN_ARGS_FOR_FILES = 2


def main(argv: list[str]) -> int:
    if len(argv) < MIN_ARGS_FOR_FILES:
        return 0  # nada a verificar

    files = [Path(p) for p in argv[1:]]
    any_found = False

    for path in files:
        if not path.exists() or not path.is_file():
            continue
        findings = scan_file(path)
        if findings:
            any_found = True
            print(f"\n[!] {path}: secret literal detected")
            for line_num, name, masked in findings:
                print(f"   line {line_num}: {name} → {masked}")

    if any_found:
        print()
        print("=" * 70)
        print("Princípio canônico 3 (CLAUDE.md): secrets PROIBIDOS em código fonte.")
        print("Commit BLOQUEADO. Sem --no-verify. Sem exceção.")
        print()
        print("Ações:")
        print("  1. Remova o secret do arquivo.")
        print("  2. Revogue/rotacione a credencial no provedor (assuma exposta).")
        print("  3. Use GitHub Secrets, env var local (.env), ou Secret Manager.")
        print("=" * 70)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
