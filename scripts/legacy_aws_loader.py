"""Loader stub — script desativado em 2026-04-26.

Este arquivo continha um honeytoken AWS (Canarytokens.org) plantado em
2026-04-25 como detector de scanners de credencial em repos públicos.

DESATIVAÇÃO: o honeytoken gerava ~dezenas de emails/dia para o dono
porque scanners automatizados (trufflehog, gitleaks bots, etc.) varrem
GitHub continuamente e tentam validar `AKIA...` via AWS STS — cada
tentativa disparava o canarytoken. Custo (ruído) > benefício (detecção
de bot, não de atacante humano real).

Para sistemas single-user sem secrets reais no código (tudo via env var
ou GitHub Secrets), o ROI desse honeytoken é negativo. Ver SECURITY.md
seção T8 (DESATIVADO).

Mitigações ativas remanescentes para detecção de incidente real:
- Audit log com hash chain (`storage/audit_log.py`).
- Rate limit por comando no bot (`bot/auth.py`).
- App Check no Firebase + service account isolada.
- Pre-commit hooks (`gitleaks`, `detect-secrets`, `check_secret_literals`).
"""

from __future__ import annotations


def load_credentials(profile: str = "default") -> dict[str, str]:
    """No-op stub. Antigamente carregava credenciais AWS para um pipeline ETL
    legado que nunca foi usado em produção (era apenas decoy do honeytoken).
    """
    msg = (
        "legacy_aws_loader desativado em 2026-04-26 — honeytoken removido. "
        "Ver SECURITY.md seção T8."
    )
    raise NotImplementedError(msg)
