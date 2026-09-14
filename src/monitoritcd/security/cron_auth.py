"""Autorização fail-closed do cron HTTP (Cloud Function)."""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping  # noqa: TC003


def cron_autorizado(headers: Mapping[str, str], *, env: Mapping[str, str] | None = None) -> bool:
    """Exige MONITOR_CRON_TOKEN e header X-Cron-Token iguais. Sem token = recusa."""
    fonte = env if env is not None else os.environ
    esperado = (fonte.get("MONITOR_CRON_TOKEN") or "").strip()
    if not esperado:
        return False
    enviado = (headers.get("X-Cron-Token") or headers.get("x-cron-token") or "").strip()
    if not enviado:
        return False
    return secrets.compare_digest(enviado, esperado)
