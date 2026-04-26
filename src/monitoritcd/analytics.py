"""Funções de análise e inteligência sobre o corpus de documentos.

Cobre IDEAS.md Categoria 7 (#221-#255). Funções puras (sem I/O), recebem
sequência de Documento e retornam estruturas serializáveis. Consumido pelo
`build_dashboard.py` e pode ser exposto via comando bot futuramente.

Itens cobertos:
- #224 trending topics (janelas 7d/30d/90d)
- #229 top fontes por relevância média
- #230 top UFs por volume
- #231 gap analysis (UFs sem novidades)
- #241 tabela comparativa de alíquotas (extraída de detect_aliquotas)
- #243 estimativa de impacto fiscal (soma valores monetários)
- #244 estatísticas de keywords
- #248 score de maturidade legislativa por UF
- #250 score de proatividade SEFAZ
- #251 score de atualidade
- #253 sazonalidade básica (mês x volume)

Itens TODO (heavy ML/análise estatística avançada):
- #225 outliers · #226 comparativo períodos
- #232-#234 tramitação metrics · #235-#239 análises cruzadas
- #240 timeline interativa · #245-#247 jurisprudência específica
- #252 predição Prophet · #254 correlação · #255 internacional

Princípios canônicos:
- Princípio 1: dados vêm de Documento já validado pydantic
- Princípio 2: limites duros em janela e top-N
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import Documento

DEFAULT_TOP_N: Final[int] = 10
DEFAULT_GAP_DAYS: Final[int] = 14
WINDOW_7D_DAYS: Final[int] = 7
WINDOW_30D_DAYS: Final[int] = 30
WINDOW_90D_DAYS: Final[int] = 90


def _now() -> datetime:
    return datetime.now(UTC)


def _within_window(doc: Documento, days: int, *, ref: datetime | None = None) -> bool:
    ref = ref or _now()
    dt = doc.original.data_publicacao or doc.original.fetched_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt >= ref - timedelta(days=days)


# ─────────────────────────────────────────────────────────────────────────────
# #224 — Trending topics (frequência por janela)
# ─────────────────────────────────────────────────────────────────────────────


def trending_topics(
    docs: Sequence[Documento],
    *,
    days: int = WINDOW_7D_DAYS,
    top_n: int = DEFAULT_TOP_N,
) -> list[tuple[str, int]]:
    """Top N temas (LLM tags + temas detectados) na janela `days`."""
    counter: Counter[str] = Counter()
    for d in docs:
        if not _within_window(d, days):
            continue
        if d.llm:
            counter.update(d.llm.tags)
            temas = d.llm.metadados_extraidos.get("temas_especificos", "")
            if temas:
                counter.update(t.strip() for t in temas.split(",") if t.strip())
    return counter.most_common(top_n)


# ─────────────────────────────────────────────────────────────────────────────
# #229 — Top fontes por relevância média
# ─────────────────────────────────────────────────────────────────────────────


def top_sources_by_relevance(
    docs: Sequence[Documento],
    *,
    top_n: int = DEFAULT_TOP_N,
    min_docs: int = 3,
) -> list[tuple[str, float, int]]:
    """Lista (source_id, avg_relevancia, n_docs) ordenada por avg desc.

    Filtra fontes com < min_docs (evita top de fonte com 1 doc score 10).
    """
    by_source: dict[str, list[int]] = {}
    for d in docs:
        if d.llm is None:
            continue
        by_source.setdefault(d.source.id, []).append(d.llm.relevancia)

    averaged: list[tuple[str, float, int]] = []
    for sid, scores in by_source.items():
        if len(scores) < min_docs:
            continue
        averaged.append((sid, sum(scores) / len(scores), len(scores)))
    averaged.sort(key=lambda x: -x[1])
    return averaged[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# #230 — Top UFs por volume
# ─────────────────────────────────────────────────────────────────────────────


def top_ufs_by_volume(
    docs: Sequence[Documento],
    *,
    top_n: int = DEFAULT_TOP_N,
) -> list[tuple[str, int]]:
    """Top N UFs por número de documentos coletados."""
    counter: Counter[str] = Counter(d.source.uf for d in docs)
    return counter.most_common(top_n)


# ─────────────────────────────────────────────────────────────────────────────
# #231 — Gap analysis (UFs sem novidades em N dias)
# ─────────────────────────────────────────────────────────────────────────────


def gap_analysis(
    docs: Sequence[Documento],
    active_ufs: Sequence[str],
    *,
    days: int = DEFAULT_GAP_DAYS,
) -> list[str]:
    """UFs ativas que não tiveram novidades em `days` dias."""
    recent_ufs: set[str] = set()
    for d in docs:
        if _within_window(d, days):
            recent_ufs.add(d.source.uf)
    return sorted(set(active_ufs) - recent_ufs)


# ─────────────────────────────────────────────────────────────────────────────
# #241 — Tabela comparativa de alíquotas
# ─────────────────────────────────────────────────────────────────────────────


def aliquotas_por_uf(docs: Sequence[Documento]) -> dict[str, list[str]]:
    """Coleta alíquotas detectadas (`detect_aliquotas`) agrupadas por UF.

    Útil para tabela comparativa estática no dashboard.
    """
    result: dict[str, list[str]] = {}
    for d in docs:
        if not d.llm:
            continue
        aliq_csv = d.llm.metadados_extraidos.get("aliquotas", "")
        if not aliq_csv:
            continue
        existing = result.setdefault(d.source.uf, [])
        for a in aliq_csv.split(","):
            a_stripped = a.strip()
            if a_stripped and a_stripped not in existing:
                existing.append(a_stripped)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# #243 — Estimativa de impacto fiscal
# ─────────────────────────────────────────────────────────────────────────────


def total_valores_monetarios_count(docs: Sequence[Documento]) -> int:
    """Total de menções a valores monetários no corpus.

    Não tenta somar valores (parsing de R$ é complexo); apenas conta
    documentos que mencionam dinheiro como sinal de impacto fiscal.
    """
    return sum(1 for d in docs if d.llm and d.llm.metadados_extraidos.get("valores_monetarios"))


# ─────────────────────────────────────────────────────────────────────────────
# #244 — Estatísticas de keywords
# ─────────────────────────────────────────────────────────────────────────────


def keyword_frequency(
    docs: Sequence[Documento],
    *,
    top_n: int = 20,
) -> list[tuple[str, int]]:
    """Frequência das tags LLM no corpus completo."""
    counter: Counter[str] = Counter()
    for d in docs:
        if d.llm:
            counter.update(d.llm.tags)
    return counter.most_common(top_n)


# ─────────────────────────────────────────────────────────────────────────────
# #248 — Score de maturidade legislativa por UF
# ─────────────────────────────────────────────────────────────────────────────


def maturity_score_per_uf(docs: Sequence[Documento]) -> dict[str, float]:
    """Score 0-1 por UF combinando: volume normalizado + relevância média + diversidade tipos.

    Formula: `0.4 * vol_norm + 0.4 * relev_norm + 0.2 * diversity`.
    """
    by_uf_volume: Counter[str] = Counter(d.source.uf for d in docs)
    by_uf_rel: dict[str, list[int]] = {}
    by_uf_tipos: dict[str, set[str]] = {}

    for d in docs:
        if not d.llm:
            continue
        by_uf_rel.setdefault(d.source.uf, []).append(d.llm.relevancia)
        by_uf_tipos.setdefault(d.source.uf, set()).add(d.llm.tipo.value)

    if not by_uf_volume:
        return {}

    max_vol = max(by_uf_volume.values()) or 1
    scores: dict[str, float] = {}
    for uf, vol in by_uf_volume.items():
        vol_norm = vol / max_vol
        rels = by_uf_rel.get(uf, [])
        rel_norm = (sum(rels) / len(rels) / 10) if rels else 0  # relev 0-10
        diversity = len(by_uf_tipos.get(uf, set())) / 9  # 9 tipos no enum
        scores[uf] = round(0.4 * vol_norm + 0.4 * rel_norm + 0.2 * diversity, 3)
    return scores


# ─────────────────────────────────────────────────────────────────────────────
# #250 — Score de proatividade SEFAZ (frequência de IN/Portaria)
# ─────────────────────────────────────────────────────────────────────────────


def sefaz_proactivity_per_uf(
    docs: Sequence[Documento],
    *,
    days: int = WINDOW_90D_DAYS,
) -> dict[str, int]:
    """Conta IN/Portaria/Resolução de SEFAZ por UF nos últimos `days` dias."""
    instrucoes = {"instrucao_normativa", "portaria", "decreto"}
    counter: Counter[str] = Counter()
    for d in docs:
        if not d.llm or not _within_window(d, days):
            continue
        if d.source.tipo.value == "sefaz" and d.llm.tipo.value in instrucoes:
            counter[d.source.uf] += 1
    return dict(counter)


# ─────────────────────────────────────────────────────────────────────────────
# #251 — Score de atualidade (idade média do corpus por UF)
# ─────────────────────────────────────────────────────────────────────────────


def actuality_score_per_uf(docs: Sequence[Documento]) -> dict[str, float]:
    """Idade média (em dias) do conteúdo coletado por UF (menor = mais atual)."""
    now = _now()
    by_uf_ages: dict[str, list[float]] = {}
    for d in docs:
        dt = d.original.data_publicacao or d.original.fetched_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age = (now - dt).total_seconds() / 86400
        by_uf_ages.setdefault(d.source.uf, []).append(age)
    return {uf: round(sum(ages) / len(ages), 1) for uf, ages in by_uf_ages.items()}


# ─────────────────────────────────────────────────────────────────────────────
# #253 — Sazonalidade (volume por mês)
# ─────────────────────────────────────────────────────────────────────────────


def seasonality_by_month(docs: Sequence[Documento]) -> dict[str, int]:
    """Conta documentos por mês (YYYY-MM) — usar para detectar sazonalidade."""
    counter: Counter[str] = Counter()
    for d in docs:
        dt = d.original.data_publicacao or d.original.fetched_at
        counter[f"{dt.year:04d}-{dt.month:02d}"] += 1
    return dict(sorted(counter.items()))


# ─────────────────────────────────────────────────────────────────────────────
# Análise consolidada (exposta no dashboard)
# ─────────────────────────────────────────────────────────────────────────────


def consolidated_report(
    docs: Sequence[Documento],
    active_ufs: Sequence[str] | None = None,
) -> dict[str, object]:
    """Relatório consolidado para dashboard ou bot.

    Estrutura serializável (JSON) com todos os principais indicadores.
    """
    return {
        "generated_at": _now().isoformat(),
        "total_docs": len(docs),
        "trending_7d": trending_topics(docs, days=WINDOW_7D_DAYS),
        "trending_30d": trending_topics(docs, days=WINDOW_30D_DAYS),
        "trending_90d": trending_topics(docs, days=WINDOW_90D_DAYS),
        "top_sources": top_sources_by_relevance(docs),
        "top_ufs": top_ufs_by_volume(docs),
        "gap_analysis": gap_analysis(docs, active_ufs or []),
        "aliquotas_por_uf": aliquotas_por_uf(docs),
        "valores_monetarios_count": total_valores_monetarios_count(docs),
        "keyword_frequency": keyword_frequency(docs),
        "maturity_score": maturity_score_per_uf(docs),
        "sefaz_proactivity": sefaz_proactivity_per_uf(docs),
        "actuality_score": actuality_score_per_uf(docs),
        "seasonality": seasonality_by_month(docs),
    }


__all__ = [
    "DEFAULT_GAP_DAYS",
    "DEFAULT_TOP_N",
    "WINDOW_7D_DAYS",
    "WINDOW_30D_DAYS",
    "WINDOW_90D_DAYS",
    "actuality_score_per_uf",
    "aliquotas_por_uf",
    "consolidated_report",
    "gap_analysis",
    "keyword_frequency",
    "maturity_score_per_uf",
    "seasonality_by_month",
    "sefaz_proactivity_per_uf",
    "top_sources_by_relevance",
    "top_ufs_by_volume",
    "total_valores_monetarios_count",
    "trending_topics",
]
