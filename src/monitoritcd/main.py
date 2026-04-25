"""Entry point CLI do MonitorITCD.

Subcomandos:
    run [--dry-run] [--source-id ID] [--uf UF]
        Executa pipeline completa (cron diário).
    seed
        Popula Firestore com active_states default a partir de
        config/active_states.default.yaml.

Uso típico (cron):
    python -m monitoritcd run

Uso em desenvolvimento:
    python -m monitoritcd run --dry-run --source-id lexml-federal
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import structlog

from monitoritcd.core.config import get_settings
from monitoritcd.llm.fake import FakeLLMProvider
from monitoritcd.orchestrator import run_pipeline
from monitoritcd.security.log_redactor import redact_sensitive
from monitoritcd.storage.in_memory import InMemoryStorage

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_DIR = REPO_ROOT / "sources"


def _make_backends(
    settings: Any,  # Settings — Any para evitar import circular em runtime  # noqa: ANN401
    *,
    dry_run: bool,
) -> tuple[Any, Any]:
    """Factory: escolhe backends de produção vs fakes.

    Estratégia:
    - `--dry-run` → sempre InMemory + FakeLLM (sem rede).
    - Modo normal → tenta wire produção (Firestore + Gemini); fallback
      para fakes se import/auth falhar (defesa em CI sem credenciais).
    """
    if dry_run:
        return InMemoryStorage(settings.OWNER_ID), FakeLLMProvider()

    # Tenta backends reais
    try:
        from google.cloud.firestore import AsyncClient  # noqa: PLC0415

        from monitoritcd.llm.gemini import GeminiProvider  # noqa: PLC0415
        from monitoritcd.storage.firestore_store import FirestoreStorage  # noqa: PLC0415

        firestore_client = AsyncClient(project=settings.FIREBASE_PROJECT_ID)
        storage: Any = FirestoreStorage(firestore_client, settings.OWNER_ID)
        llm: Any = GeminiProvider(settings.GEMINI_API_KEY)
    except (ImportError, RuntimeError) as e:
        # Defesa: se ambiente real não disponível, cai pro fake e loga
        log = structlog.get_logger("main")
        log.warning("backends.fallback_to_fake", reason=str(e))
        return InMemoryStorage(settings.OWNER_ID), FakeLLMProvider()

    return storage, llm


def configure_logging(level: str = "INFO") -> None:
    """Configura `structlog` JSON com redator de secrets."""
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        cache_logger_on_first_use=True,
    )


async def cmd_run(args: argparse.Namespace) -> int:
    """Subcomando `run`."""
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    log = structlog.get_logger("main")

    log.info(
        "cli.run.start",
        dry_run=args.dry_run,
        source_id=args.source_id,
        uf=args.uf,
    )

    storage, llm = _make_backends(settings, dry_run=args.dry_run)

    report = await run_pipeline(
        settings,
        storage=storage,
        llm_provider=llm,
        sources_dir=SOURCES_DIR,
        only_source_id=args.source_id,
        only_uf=args.uf,
    )

    log.info(
        "cli.run.done",
        run_id=report.run_id,
        duration_s=report.duration_seconds,
        sources=report.sources_consulted,
        failed=report.sources_failed,
        items_stored=report.items_stored,
    )

    return 0 if report.sources_failed == 0 else 1


def cli(argv: list[str] | None = None) -> int:
    """Entry point do CLI."""
    parser = argparse.ArgumentParser(
        prog="monitoritcd",
        description="MonitorITCD — sistema de monitoramento ITCD/Sucessões/Regime de Bens",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Executa pipeline completa")
    run_p.add_argument("--dry-run", action="store_true", help="Não persiste nem notifica")
    run_p.add_argument("--source-id", type=str, default=None, help="Apenas uma fonte")
    run_p.add_argument("--uf", type=str, default=None, help="Apenas UFs específicas")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        return asyncio.run(cmd_run(args))

    parser.print_help()  # pragma: no cover
    return 1  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
