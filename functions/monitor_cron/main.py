"""Cloud Function HTTPS — pipeline diária (substitui o cron do GitHub Actions)."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path

import functions_framework
from flask import Request, Response

logger = logging.getLogger("monitor_cron")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _autorizado(request: Request) -> bool:
    """Fail-closed: sem MONITOR_CRON_TOKEN ou sem header, recusa."""
    esperado = (os.environ.get("MONITOR_CRON_TOKEN") or "").strip()
    if not esperado:
        return False
    enviado = (request.headers.get("X-Cron-Token") or "").strip()
    if not enviado:
        return False
    return secrets.compare_digest(enviado, esperado)


@functions_framework.http
def monitor_cron(request: Request) -> Response:
    if request.method not in {"POST", "GET"}:
        return Response("method not allowed", status=405)
    if not _autorizado(request):
        return Response("unauthorized", status=401)

    raiz = Path(os.environ.get("MONITORITCD_ROOT") or Path(__file__).resolve().parent)
    os.environ.setdefault("MONITORITCD_ROOT", str(raiz))
    os.environ.setdefault("ENV", "production")

    from monitoritcd.core.config import get_settings  # noqa: PLC0415
    from monitoritcd.main import _make_backends  # noqa: PLC0415
    from monitoritcd.orchestrator import run_pipeline  # noqa: PLC0415
    from monitoritcd.painel.persistencia import materializar_operador  # noqa: PLC0415

    materializar_operador(raiz)
    settings = get_settings()
    storage, llm = _make_backends(settings, dry_run=False)
    sources_dir = raiz / "sources"
    report = asyncio.run(
        run_pipeline(
            settings,
            storage=storage,
            llm_provider=llm,
            sources_dir=sources_dir,
        )
    )
    corpo = (
        f"ok collected={report.items_collected} classified={report.items_classified} "
        f"telegram={report.items_notified_telegram}\n"
    )
    logger.info("monitor_cron.done %s", corpo.strip())
    return Response(corpo, status=200, mimetype="text/plain")
