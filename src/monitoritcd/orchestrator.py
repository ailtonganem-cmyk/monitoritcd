"""Orquestrador da pipeline de coleta → filtragem → classificação → notificação.

Pipeline single-run (uma execução de cron):

    sources/*.yaml
         │
         ▼
    [Collectors] (paralelos por fonte, isolados em try/except)
         │
         ▼
    RawItems
         │
         ▼
    [Filtro 1: keywords]
         │
         ▼
    [Filtro 2: prescore heurístico]
         │
         ▼
    [Filtro 3: dedup por hash]
         │
         ▼
    [Classifier LLM] (em batches de MAX_BATCH_LLM)
         │
         ▼
    [Storage: save_documento]
         │
         ▼
    [Notifier: digest + push imediato para CRITICO]
         │
         ▼
    [Audit log + Healthcheck ping]

Princípios canônicos aplicados:
- Falha em uma fonte NÃO derruba pipeline (try/except por fonte).
- Tudo logado via `structlog` JSON com `correlation_id` por execução.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — usado em runtime
from typing import TYPE_CHECKING

import httpx
import structlog

from monitoritcd.collectors import (
    GenericHTMLCollector,
    GenericRSSCollector,
    LexMLCollector,
)
from monitoritcd.core.models import (
    Documento,
    Parser,
    SeverityTier,
    StatusDocumento,
)
from monitoritcd.core.source_loader import load_all_sources
from monitoritcd.dedup import assign_clusters
from monitoritcd.filters.keywords import KEYWORDS_DEFAULT, matches_keywords
from monitoritcd.filters.llm_classifier import classify_with_provider
from monitoritcd.filters.prescore import passes_cutoff, prescore
from monitoritcd.storage.audit_log import AuditLog

if TYPE_CHECKING:
    from monitoritcd.core.base_collector import BaseCollector
    from monitoritcd.core.config import Settings
    from monitoritcd.core.models import RawItem, Source
    from monitoritcd.filters.llm_classifier import LLMProvider
    from monitoritcd.storage.base import StorageProtocol

logger = structlog.get_logger(__name__)

_PARSERS_TO_COLLECTORS = {
    Parser.GENERIC_RSS: GenericRSSCollector,
    Parser.GENERIC_HTML: GenericHTMLCollector,
    Parser.LEXML: LexMLCollector,
}


@dataclass
class RunReport:
    """Relatório de uma execução do orquestrador."""

    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    sources_consulted: int = 0
    sources_failed: int = 0
    items_collected: int = 0
    items_after_keywords: int = 0
    items_after_prescore: int = 0
    items_new: int = 0  # passaram dedup
    items_classified: int = 0
    items_stored: int = 0
    items_notified_email: int = 0
    items_notified_telegram: int = 0
    failed_sources: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.finished_at is None:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()


def make_collector(source: Source) -> BaseCollector:
    """Factory: constrói o coletor apropriado para a fonte."""
    cls = _PARSERS_TO_COLLECTORS.get(source.parser)
    if cls is None:  # pragma: no cover - extra parser
        msg = f"Parser não suportado: {source.parser}"
        raise ValueError(msg)
    return cls(source)


async def collect_from_source(source: Source) -> list[RawItem]:
    """Coleta items de uma fonte. Encapsula context manager + erros."""
    collector = make_collector(source)
    async with collector as c:
        return await c.collect()


def filter_by_keywords(
    items: list[tuple[Source, RawItem]],
) -> list[tuple[Source, RawItem, list[str]]]:
    """Aplica filtro 1 (keywords). Retorna items aprovados + keywords encontradas."""
    out: list[tuple[Source, RawItem, list[str]]] = []
    for source, item in items:
        text = (item.titulo_raw or "") + " " + (item.texto_raw or "")
        kws = source.keywords_required or list(KEYWORDS_DEFAULT)
        matched, found = matches_keywords(text, kws)
        if matched:
            out.append((source, item, found))
    return out


def filter_by_prescore(
    items: list[tuple[Source, RawItem, list[str]]],
) -> list[tuple[Source, RawItem]]:
    """Aplica filtro 2 (prescore). Cutoff = DEFAULT_CUTOFF (0.3)."""
    out: list[tuple[Source, RawItem]] = []
    for source, item, kws in items:
        score = prescore(item, source, kws)
        if passes_cutoff(score):
            out.append((source, item))
    return out


async def filter_by_dedup(
    items: list[tuple[Source, RawItem]],
    storage: StorageProtocol,
) -> list[tuple[Source, RawItem]]:
    """Filtra items já armazenados (dedup persistente)."""
    out: list[tuple[Source, RawItem]] = []
    for source, item in items:
        if await storage.exists_by_hash(item.content_hash):
            continue
        out.append((source, item))
    return out


async def classify_and_store(
    items: list[tuple[Source, RawItem]],
    *,
    llm_provider: LLMProvider,
    storage: StorageProtocol,
    owner_id: str,
    report: RunReport,
) -> list[Documento]:
    """Classifica via LLM (batches) e persiste."""
    from monitoritcd.core import limits as _lim  # noqa: PLC0415

    if not items:
        return []

    # Atribui cluster_ids
    raw_items = [item for _, item in items]
    cluster_map = assign_clusters(raw_items)

    docs_saved: list[Documento] = []
    for batch_start in range(0, len(items), _lim.MAX_BATCH_LLM):
        batch = items[batch_start : batch_start + _lim.MAX_BATCH_LLM]
        try:
            llm_results = await classify_with_provider(
                [it for _, it in batch],
                llm_provider,
                llm_model=llm_provider.name,
            )
        except (ValueError, TimeoutError) as e:
            logger.exception("classify.batch_failed", error=str(e))
            report.errors.append(f"classify_batch: {e}")
            continue

        for (source, item), llm_result in zip(batch, llm_results, strict=True):
            # Descarta se LLM marcou como descartado
            if llm_result.severity_tier == SeverityTier.DESCARTADO:
                continue

            doc_id = f"{source.id}:{item.content_hash[:16]}"
            doc = Documento(
                owner_id=owner_id,
                doc_id=doc_id,
                source=source,
                original=item,
                llm=llm_result,
                status=StatusDocumento.CLASSIFIED,
                cluster_id=cluster_map.get(item.content_hash),
            )
            try:
                await storage.save_documento(doc)
                docs_saved.append(doc)
                report.items_stored += 1
            except (ValueError, RuntimeError) as e:
                logger.exception(
                    "storage.save_failed",
                    doc_id=doc_id,
                    error=str(e),
                )
                report.errors.append(f"save_documento {doc_id}: {e}")

        report.items_classified += len(llm_results)

    return docs_saved


async def ping_healthcheck(settings: Settings, *, success: bool = True) -> None:
    """Faz GET ao endpoint Healthchecks.io. Falha silenciosa (best-effort)."""
    if settings.HEALTHCHECKS_URL is None:
        return
    url = str(settings.HEALTHCHECKS_URL)
    if not success:
        url = url.rstrip("/") + "/fail"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            await client.get(url)
    except httpx.HTTPError as e:
        logger.warning("healthcheck.failed", error=str(e))


async def run_pipeline(
    settings: Settings,
    *,
    storage: StorageProtocol,
    llm_provider: LLMProvider,
    sources_dir: Path,
    only_source_id: str | None = None,
    only_uf: str | None = None,
) -> RunReport:
    """Executa pipeline completa. Retorna `RunReport`."""
    run_id = str(uuid.uuid4())
    report = RunReport(run_id=run_id, started_at=datetime.now(UTC))
    audit = AuditLog(storage)

    bound = logger.bind(run_id=run_id)
    bound.info("run.start")

    # 1. Filtra sources por active_states + flags
    all_sources = load_all_sources(sources_dir, ativo_only=True)
    active = await storage.get_active_states()
    active_ufs = set(active.active_uf) if active else set()
    federal_active = active.federal_active if active else True

    sources_to_run: list[Source] = []
    for s in all_sources:
        if only_source_id and s.id != only_source_id:
            continue
        if only_uf and s.uf != only_uf:
            continue
        if s.uf == "_federal":
            if federal_active:
                sources_to_run.append(s)
        elif s.uf in active_ufs:
            sources_to_run.append(s)

    bound.info("run.sources_filtered", total=len(sources_to_run))

    # 2. Coleta paralela
    raw_items: list[tuple[Source, RawItem]] = []
    tasks = [collect_from_source(s) for s in sources_to_run]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for source, result in zip(sources_to_run, results, strict=True):
        report.sources_consulted += 1
        if isinstance(result, BaseException):
            report.sources_failed += 1
            report.failed_sources.append(source.id)
            bound.warning(
                "source.failed",
                source=source.id,
                error=type(result).__name__,
                message=str(result),
            )
            continue
        for item in result:
            raw_items.append((source, item))
    report.items_collected = len(raw_items)
    bound.info("run.collected", count=len(raw_items))

    # 3. Filtro 1: keywords
    after_kw = filter_by_keywords(raw_items)
    report.items_after_keywords = len(after_kw)

    # 4. Filtro 2: prescore
    after_score = filter_by_prescore(after_kw)
    report.items_after_prescore = len(after_score)

    # 5. Filtro 3: dedup persistente
    new_items = await filter_by_dedup(after_score, storage)
    report.items_new = len(new_items)
    bound.info("run.filtered", new=len(new_items))

    # 6. Classify + store
    if new_items:
        await classify_and_store(
            new_items,
            llm_provider=llm_provider,
            storage=storage,
            owner_id=settings.OWNER_ID,
            report=report,
        )

    # 7. Audit
    try:
        await audit.append(
            actor="system:cron",
            action="run.complete",
            payload={
                "run_id": run_id,
                "sources_consulted": report.sources_consulted,
                "items_stored": report.items_stored,
            },
        )
    except (ValueError, RuntimeError) as e:
        bound.warning("audit.failed", error=str(e))

    # 8. Healthcheck ping (sucesso)
    await ping_healthcheck(settings, success=True)

    report.finished_at = datetime.now(UTC)
    bound.info(
        "run.complete",
        duration_s=report.duration_seconds,
        stored=report.items_stored,
        failed_sources=report.sources_failed,
    )
    return report
