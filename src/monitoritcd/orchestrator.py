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
    ALEPCollector,
    ALEPECollector,
    ALMGCollector,
    CamaraDeputadosCollector,
    GenericHTMLCollector,
    GenericRSSCollector,
    LexMLCollector,
    LexMLPortalCollector,
    SAPLCollector,
    SenadoCollector,
)
from monitoritcd.core.models import (
    Documento,
    NotificacaoStatus,
    Parser,
    SeverityTier,
    StatusDocumento,
)
from monitoritcd.core.source_loader import load_all_sources
from monitoritcd.dedup import assign_clusters
from monitoritcd.filters.keywords import KEYWORDS_DEFAULT, matches_keywords
from monitoritcd.filters.llm_classifier import classify_with_provider
from monitoritcd.filters.prescore import passes_cutoff, prescore
from monitoritcd.llm.fallback import LLMProvidersExhaustedError
from monitoritcd.notifiers.email_notifier import EmailNotifier
from monitoritcd.notifiers.telegram_notifier import TelegramNotifier
from monitoritcd.storage.audit_log import AuditChainError, AuditLog

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
    Parser.LEXML_PORTAL: LexMLPortalCollector,
    Parser.ALMG: ALMGCollector,
    Parser.ALEP: ALEPCollector,
    Parser.ALEPE: ALEPECollector,
    Parser.SAPL: SAPLCollector,
    Parser.CAMARA_DEPUTADOS: CamaraDeputadosCollector,
    Parser.SENADO: SenadoCollector,
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


def make_collector(
    source: Source,
    *,
    proxy_br_url: str | None = None,
    proxy_br_token: str | None = None,
) -> BaseCollector:
    """Factory: constrói o coletor apropriado para a fonte."""
    cls = _PARSERS_TO_COLLECTORS.get(source.parser)
    if cls is None:  # pragma: no cover - extra parser
        msg = f"Parser não suportado: {source.parser}"
        raise ValueError(msg)
    return cls(source, proxy_br_url=proxy_br_url, proxy_br_token=proxy_br_token)


async def collect_from_source(
    source: Source,
    *,
    proxy_br_url: str | None = None,
    proxy_br_token: str | None = None,
) -> list[RawItem]:
    """Coleta items de uma fonte. Encapsula context manager + erros."""
    collector = make_collector(source, proxy_br_url=proxy_br_url, proxy_br_token=proxy_br_token)
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
    for batch_idx, batch_start in enumerate(range(0, len(items), _lim.MAX_BATCH_LLM)):
        batch = items[batch_start : batch_start + _lim.MAX_BATCH_LLM]
        # Throttle entre batches respeita rate limit do provedor (Groq Free: 30 RPM).
        # O primeiro batch corre direto; demais aguardam LLM_BATCH_DELAY_SECONDS.
        if batch_idx > 0:
            await asyncio.sleep(_lim.LLM_BATCH_DELAY_SECONDS)
        try:
            llm_results = await classify_with_provider(
                [it for _, it in batch],
                llm_provider,
                llm_model=llm_provider.name,
            )
        except LLMProvidersExhaustedError as e:
            # Tier 3: ambos LLMs em quota. Defere classificação salvando os
            # itens como pending (sem llm). Próxima execução tenta classificar.
            logger.warning(
                "classify.batch_deferred_quota_exhausted",
                batch_size=len(batch),
                error=str(e),
            )
            report.errors.append(f"classify_deferred ({len(batch)} items): quota exhausted")
            for source, item in batch:
                doc_id = f"{source.id}:{item.content_hash[:16]}"
                deferred = Documento(
                    owner_id=owner_id,
                    doc_id=doc_id,
                    source=source,
                    original=item,
                    llm=None,  # write-once original; llm fica nulo até próxima exec
                    status=StatusDocumento.PENDING,
                    cluster_id=cluster_map.get(item.content_hash),
                )
                try:
                    await storage.save_documento(deferred)
                    report.items_stored += 1
                except (ValueError, RuntimeError) as save_exc:
                    logger.exception(
                        "storage.save_deferred_failed",
                        doc_id=doc_id,
                        error=str(save_exc),
                    )
            continue
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


async def reprocess_documents(
    *,
    storage: StorageProtocol,
    llm_provider: LLMProvider,
    since: datetime | None = None,
    uf: str | None = None,
    limit: int = 200,
) -> RunReport:
    """Reclassifica documentos existentes com prompt/modelo atual.

    Não modifica `original.*` (write-once) — só sobrescreve `llm.*`.
    Útil quando o prompt é melhorado ou modelo é trocado.
    """
    from monitoritcd.core import limits as _lim  # noqa: PLC0415

    run_id = str(uuid.uuid4())
    report = RunReport(run_id=run_id, started_at=datetime.now(UTC))
    bound = logger.bind(run_id=run_id)
    bound.info("reprocess.start", since=str(since) if since else None, uf=uf)

    docs = await storage.list_documentos(since=since, uf=uf, limit=limit)
    bound.info("reprocess.docs_loaded", count=len(docs))

    if not docs:
        report.finished_at = datetime.now(UTC)
        return report

    for batch_idx, batch_start in enumerate(range(0, len(docs), _lim.MAX_BATCH_LLM)):
        batch = docs[batch_start : batch_start + _lim.MAX_BATCH_LLM]
        # Throttle entre batches em reprocessamento (mesmo motivo de classify_and_store).
        if batch_idx > 0:
            await asyncio.sleep(_lim.LLM_BATCH_DELAY_SECONDS)
        try:
            llm_results = await classify_with_provider(
                [d.original for d in batch],
                llm_provider,
                llm_model=llm_provider.name,
            )
        except (ValueError, TimeoutError) as e:
            bound.exception("reprocess.classify_failed", error=str(e))
            report.errors.append(f"reprocess_classify: {e}")
            continue

        for doc, new_llm in zip(batch, llm_results, strict=True):
            try:
                await storage.update_llm(doc.doc_id, new_llm)
                report.items_classified += 1
            except (ValueError, RuntimeError) as e:
                bound.warning("reprocess.update_failed", doc_id=doc.doc_id, error=str(e))

    report.finished_at = datetime.now(UTC)
    bound.info("reprocess.complete", classified=report.items_classified)
    return report


async def notify_documents(
    docs: list[Documento],
    *,
    settings: Settings,
    storage: StorageProtocol,
    report: RunReport,
    digest_label: str = "Diário",
) -> None:
    """Envia notificações: push imediato para CRITICO, digest para o resto.

    Estratégia:
    - Itens com `severity_tier=CRITICO` → push imediato no Telegram (cada um).
    - Demais (ALTA/NORMAL/BAIXA) → consolidados num digest (Telegram + Email).
    - DESCARTADO já foi removido em `classify_and_store`.

    Princípios canônicos:
    - Falha em um canal não impede o outro.
    - Exceções não derrubam pipeline (capturadas e logadas).
    """
    if not docs:
        return

    now = datetime.now(UTC)

    criticos = [d for d in docs if d.llm and d.llm.severity_tier == SeverityTier.CRITICO]
    digest_docs = [d for d in docs if d.llm and d.llm.severity_tier != SeverityTier.CRITICO]

    # 1. Push imediato dos CRITICO (1 mensagem por item)
    if criticos:
        try:
            async with TelegramNotifier(settings) as tg:
                for doc in criticos:
                    await tg.send_digest([doc], digest_label="🔴 CRÍTICO", data_geracao=now)
                    report.items_notified_telegram += 1
                    await storage.update_notificacao(
                        doc.doc_id,
                        NotificacaoStatus(
                            enviada=True,
                            enviada_em=now,
                            canais=["telegram"],
                        ),
                    )
                    await storage.update_status(doc.doc_id, StatusDocumento.NOTIFIED)
        except Exception as e:  # last-resort - notif não pode derrubar pipeline
            logger.exception("notify.critico_failed", error=str(e))
            report.errors.append(f"notify_critico: {e}")

    # 2. Digest consolidado (Telegram + Email) para o resto
    if digest_docs:
        # Telegram
        try:
            async with TelegramNotifier(settings) as tg:
                await tg.send_digest(digest_docs, digest_label=digest_label, data_geracao=now)
                report.items_notified_telegram += len(digest_docs)
        except Exception as e:
            logger.exception("notify.digest_telegram_failed", error=str(e))
            report.errors.append(f"notify_digest_telegram: {e}")

        # Email (digest único)
        try:
            email_notifier = EmailNotifier(settings)
            await email_notifier.send_digest(
                digest_docs,
                digest_label=digest_label,
                data_geracao=now,
            )
            report.items_notified_email += len(digest_docs)
        except Exception as e:
            logger.exception("notify.digest_email_failed", error=str(e))
            report.errors.append(f"notify_digest_email: {e}")

        # Marca como notificado
        for doc in digest_docs:
            try:
                await storage.update_notificacao(
                    doc.doc_id,
                    NotificacaoStatus(
                        enviada=True,
                        enviada_em=now,
                        canais=["telegram", "email"],
                    ),
                )
                await storage.update_status(doc.doc_id, StatusDocumento.NOTIFIED)
            except (ValueError, RuntimeError) as e:
                logger.warning("notify.status_update_failed", doc_id=doc.doc_id, error=str(e))


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


async def _select_sources(
    sources_dir: Path,
    storage: StorageProtocol,
    *,
    only_source_id: str | None,
    only_uf: str | None,
    skip_geo_restricted: bool = False,
    only_geo_restricted: bool = False,
) -> list[Source]:
    """Filtra fontes ativas por active_states + flags de execução."""
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
        if skip_geo_restricted and s.geo_restricted:
            continue
        if only_geo_restricted and not s.geo_restricted:
            continue
        if s.uf == "_federal":
            if federal_active:
                sources_to_run.append(s)
        elif s.uf in active_ufs:
            sources_to_run.append(s)
    return sources_to_run


async def _collect_all(
    sources: list[Source],
    report: RunReport,
    bound: structlog.BoundLogger,
    *,
    proxy_br_url: str | None = None,
    proxy_br_token: str | None = None,
) -> list[tuple[Source, RawItem]]:
    """Coleta paralela; isola falhas por fonte."""
    raw_items: list[tuple[Source, RawItem]] = []
    tasks = [
        collect_from_source(s, proxy_br_url=proxy_br_url, proxy_br_token=proxy_br_token)
        for s in sources
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for source, result in zip(sources, results, strict=True):
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
        raw_items.extend((source, item) for item in result)
    report.items_collected = len(raw_items)
    return raw_items


async def run_pipeline(
    settings: Settings,
    *,
    storage: StorageProtocol,
    llm_provider: LLMProvider,
    sources_dir: Path,
    only_source_id: str | None = None,
    only_uf: str | None = None,
    skip_geo_restricted: bool = False,
    only_geo_restricted: bool = False,
    notify: bool = True,
) -> RunReport:
    """Executa pipeline completa. Retorna `RunReport`."""
    run_id = str(uuid.uuid4())
    report = RunReport(run_id=run_id, started_at=datetime.now(UTC))
    audit = AuditLog(storage)
    bound = logger.bind(run_id=run_id)
    bound.info("run.start")

    # Sugestão #25: validação leve da chain de audit em runtime.
    # Apenas checa as últimas N entries (custo O(N), N=20). Detecção de
    # tampering recente sem inviabilizar performance.
    try:
        recent_audit = await storage.list_audit_recent(limit=20)
        if recent_audit:
            await audit.verify_chain(recent_audit)
    except AttributeError:
        # Storage backend sem list_audit_recent — pula silenciosamente.
        bound.debug("run.audit_chain_check_unavailable")
    except (AuditChainError, ValueError) as e:
        # Chain corrompida — alerta crítico, mas não derruba pipeline.
        bound.error("run.audit_chain_corruption", error=str(e))
        report.errors.append(f"audit_chain_corruption: {e}")

    # 1. Selecionar fontes ativas
    sources_to_run = await _select_sources(
        sources_dir,
        storage,
        only_source_id=only_source_id,
        only_uf=only_uf,
        skip_geo_restricted=skip_geo_restricted,
        only_geo_restricted=only_geo_restricted,
    )
    bound.info("run.sources_filtered", total=len(sources_to_run))

    # 2. Coleta paralela (com fallback via proxy BR para fontes geo_restricted)
    proxy_url = str(settings.PROXY_BR_URL) if settings.PROXY_BR_URL else None
    proxy_token = settings.PROXY_BR_TOKEN.get_secret_value() if settings.PROXY_BR_TOKEN else None
    raw_items = await _collect_all(
        sources_to_run,
        report,
        bound,
        proxy_br_url=proxy_url,
        proxy_br_token=proxy_token,
    )
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
    docs_saved: list[Documento] = []
    if new_items:
        docs_saved = await classify_and_store(
            new_items,
            llm_provider=llm_provider,
            storage=storage,
            owner_id=settings.OWNER_ID,
            report=report,
        )

    # 7. Notificações (push CRITICO imediato + digest)
    if notify and docs_saved:
        await notify_documents(
            docs_saved,
            settings=settings,
            storage=storage,
            report=report,
        )

    # 8. Audit
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

    # 9. Healthcheck ping (sucesso)
    await ping_healthcheck(settings, success=True)

    report.finished_at = datetime.now(UTC)
    bound.info(
        "run.complete",
        duration_s=report.duration_seconds,
        stored=report.items_stored,
        failed_sources=report.sources_failed,
    )
    return report
