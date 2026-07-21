"""Entry point CLI do MonitorITCD.

Subcomandos:
    run [--dry-run] [--source-id ID] [--uf UF]
        Executa pipeline completa (cron diário).
    digest --periodicidade {semanal,mensal} [--dry-run]
        Envia rollup agregado (Telegram + Email) dos documentos já
        classificados na janela (IDEAS.md #101/#102).
    seed
        Popula Firestore com active_states default a partir de
        config/active_states.default.yaml.

Uso típico (cron):
    python -m monitoritcd.main run
    python -m monitoritcd.main digest --periodicidade semanal

Uso em desenvolvimento:
    python -m monitoritcd.main run --dry-run --source-id lexml-federal
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

        from monitoritcd.llm.fallback import FallbackLLMProvider  # noqa: PLC0415
        from monitoritcd.llm.gemini import GeminiProvider  # noqa: PLC0415
        from monitoritcd.llm.groq import GroqProvider  # noqa: PLC0415
        from monitoritcd.storage.firestore_store import FirestoreStorage  # noqa: PLC0415

        firestore_client = AsyncClient(project=settings.FIREBASE_PROJECT_ID)
        storage: Any = FirestoreStorage(firestore_client, settings.OWNER_ID)

        # Decisão do dono (2026-07-08): escopo geográfico reduzido a MG + fontes
        # federais derruba o volume diário processado pelo LLM, então a cota free
        # do Gemini (20 req/dia/modelo) volta a ser suficiente. Gemini retorna a
        # ser o provedor primário; Groq permanece como fallback para absorver
        # oscilações de rede ou 429 momentâneo. Sem GROQ_API_KEY, mantém Gemini-only.
        gemini = GeminiProvider(settings.GEMINI_API_KEY)
        if settings.GROQ_API_KEY:
            llm: Any = FallbackLLMProvider(
                primary=gemini, fallback=GroqProvider(settings.GROQ_API_KEY)
            )
        else:
            llm = gemini
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
        skip_geo_restricted=args.skip_geo_restricted,
        only_geo_restricted=args.only_geo_restricted,
        notify=not args.dry_run,
    )

    log.info(
        "cli.run.done",
        run_id=report.run_id,
        duration_s=report.duration_seconds,
        sources=report.sources_consulted,
        failed=report.sources_failed,
        items_stored=report.items_stored,
    )

    # Exit code semantics:
    # - 0: pelo menos uma fonte rodou (sucesso parcial e aceitavel - sites oscilam)
    # - 1: nenhuma fonte rodou OU todas falharam (config/rede grave)
    if report.sources_consulted == 0:
        log.error("cli.run.no_sources", reason="nenhuma fonte ativa encontrada")
        return 1
    if report.sources_failed == report.sources_consulted:
        log.error("cli.run.all_sources_failed", failed=report.failed_sources)
        return 1
    return 0


async def cmd_reprocess(args: argparse.Namespace) -> int:
    """Subcomando `reprocess` — reclassifica documentos existentes."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from monitoritcd.orchestrator import reprocess_documents  # noqa: PLC0415

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    log = structlog.get_logger("main")

    since: datetime | None = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
        except ValueError:
            log.error("cli.reprocess.invalid_since", value=args.since)
            return 1

    storage, llm = _make_backends(settings, dry_run=False)

    log.info("cli.reprocess.start", since=str(since), uf=args.uf, limit=args.limit)
    report = await reprocess_documents(
        storage=storage,
        llm_provider=llm,
        since=since,
        uf=args.uf,
        limit=args.limit,
    )
    log.info(
        "cli.reprocess.done",
        run_id=report.run_id,
        classified=report.items_classified,
        duration_s=report.duration_seconds,
    )
    return 0


async def cmd_digest(args: argparse.Namespace) -> int:
    """Subcomando `digest` — envia rollup semanal/mensal (IDEAS.md #101/#102)."""
    from monitoritcd.orchestrator import run_digest  # noqa: PLC0415

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    log = structlog.get_logger("main")

    storage, _llm = _make_backends(settings, dry_run=args.dry_run)

    log.info("cli.digest.start", periodicidade=args.periodicidade, dry_run=args.dry_run)
    report = await run_digest(
        settings,
        storage=storage,
        periodicidade=args.periodicidade,
    )
    log.info(
        "cli.digest.done",
        run_id=report.run_id,
        classified=report.items_classified,
        notified_telegram=report.items_notified_telegram,
        notified_email=report.items_notified_email,
        errors=len(report.errors),
        duration_s=report.duration_seconds,
    )
    return 1 if report.errors else 0


async def cmd_reindex_search(args: argparse.Namespace) -> int:
    """Subcomando `reindex-search` — materializa corpus pesquisável em documentos."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from monitoritcd.orchestrator import reindex_search_indexes  # noqa: PLC0415

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    log = structlog.get_logger("main")

    since: datetime | None = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
        except ValueError:
            log.error("cli.reindex_search.invalid_since", value=args.since)
            return 1

    storage, _llm = _make_backends(settings, dry_run=False)

    log.info(
        "cli.reindex_search.start",
        since=str(since),
        uf=args.uf,
        limit=args.limit,
        missing_only=not args.all,
    )
    report = await reindex_search_indexes(
        storage=storage,
        since=since,
        uf=args.uf,
        limit=args.limit,
        missing_only=not args.all,
    )
    log.info(
        "cli.reindex_search.done",
        run_id=report.run_id,
        scanned=report.items_collected,
        reindexed=report.items_reindexed,
        errors=len(report.errors),
        duration_s=report.duration_seconds,
    )
    return 1 if report.errors else 0


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
    geo = run_p.add_mutually_exclusive_group()
    geo.add_argument(
        "--skip-geo-restricted",
        action="store_true",
        help="Pula fontes geo_restricted=true (default em CI / GitHub runner)",
    )
    geo.add_argument(
        "--only-geo-restricted",
        action="store_true",
        help="Coleta APENAS fontes geo_restricted=true (worker local Windows)",
    )

    rep_p = sub.add_parser("reprocess", help="Reclassifica documentos existentes (LLM apenas)")
    rep_p.add_argument(
        "--since",
        type=str,
        default=None,
        help="Data inicial (ISO 8601: YYYY-MM-DD)",
    )
    rep_p.add_argument("--uf", type=str, default=None, help="Apenas uma UF")
    rep_p.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Máximo de documentos a reprocessar",
    )

    digest_p = sub.add_parser(
        "digest",
        help="Envia digest agregado (semanal/mensal) — IDEAS.md #101/#102",
    )
    digest_p.add_argument(
        "--periodicidade",
        type=str,
        choices=["semanal", "mensal"],
        required=True,
    )
    digest_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Usa storage in-memory (sem Firestore nem envio real)",
    )

    reidx_p = sub.add_parser(
        "reindex-search",
        help="Regenera o índice de busca materializado dos documentos",
    )
    reidx_p.add_argument(
        "--since",
        type=str,
        default=None,
        help="Data inicial (ISO 8601: YYYY-MM-DD)",
    )
    reidx_p.add_argument("--uf", type=str, default=None, help="Apenas uma UF")
    reidx_p.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Tamanho do lote por página; a reindexação varre todas as páginas",
    )
    reidx_p.add_argument(
        "--all",
        action="store_true",
        help="Recalcula também documentos que já têm search_index",
    )

    args = parser.parse_args(argv)

    if args.cmd == "run":
        return asyncio.run(cmd_run(args))
    if args.cmd == "reprocess":
        return asyncio.run(cmd_reprocess(args))
    if args.cmd == "reindex-search":
        return asyncio.run(cmd_reindex_search(args))
    if args.cmd == "digest":
        return asyncio.run(cmd_digest(args))

    parser.print_help()  # pragma: no cover
    return 1  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
