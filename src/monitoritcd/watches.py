"""Engine de matching de watch list (Categoria 9 IDEAS.md).

Avalia se um Documento corresponde a um Watch, suportando múltiplos tipos
de pattern, expiração, cooldown, similaridade fuzzy, e templates pré-definidos.

Itens cobertos:
- #281 term · #282 pl_number · #283 uf_topic · #286 regex
- #287 expressão lógica · #289 expiração · #290 prioridade
- #291 alta relevância · #292 qualquer match · #293 cooldown
- #294 export JSON (model_dump) · #297 similaridade > 0.85
- #298 tipo · #299 alíquota · #300 revogação · #301 modulação
- #302 cluster · #305 templates de watch

Itens TODO/UI:
- #284 relator (parcial via search) · #285 tribunal (parcial)
- #295 derivado de busca (orquestração externa)
- #296 hash exato (já no dedup)
- #303-#304 sequência de tramitação (requer state machine)

Princípios canônicos:
- Princípio 1: pattern de regex/term validado (max len, regex compile try/except)
- Princípio 3: cooldown previne notification spam
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from monitoritcd.search import boolean_search, fuzzy_search, regex_search

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import Documento, Watch

SIMILAR_HIGH_THRESHOLD: Final[float] = 0.85
DEFAULT_COOLDOWN_HOURS: Final[int] = 24


# ─────────────────────────────────────────────────────────────────────────────
# Templates de watch (#305)
# ─────────────────────────────────────────────────────────────────────────────


def get_templates() -> list[dict[str, str]]:
    """#305 — Templates pré-definidos de watch.

    Retorna lista de templates com (name, pattern, pattern_type) que podem
    ser instanciados via /observar template=NAME no bot.
    """
    return [
        {
            "name": "aliquota_sp",
            "pattern": "alíquota.*SP|SP.*alíquota",
            "pattern_type": "regex",
            "description": "Mudanças de alíquota ITCMD em SP",
        },
        {
            "name": "holding_familiar",
            "pattern": "holding familiar",
            "pattern_type": "term",
            "description": "Discussões sobre holding familiar",
        },
        {
            "name": "pec_itcd_federal",
            "pattern": "PEC.*ITCD|ITCD.*federal|unificação.*ITCD",
            "pattern_type": "regex",
            "description": "PEC sobre ITCD federal / unificação",
        },
        {
            "name": "modulacao_efeitos",
            "pattern": "modulação de efeitos",
            "pattern_type": "term",
            "description": "Decisões com modulação de efeitos",
        },
        {
            "name": "stf_repercussao",
            "pattern": "Tema.*STF|repercussão geral",
            "pattern_type": "regex",
            "description": "Decisões STF com repercussão geral",
        },
        {
            "name": "doacao_usufruto",
            "pattern": "doação com reserva de usufruto",
            "pattern_type": "term",
            "description": "Doação com reserva de usufruto",
        },
        {
            "name": "offshore",
            "pattern": "offshore",
            "pattern_type": "term",
            "description": "Sucessão internacional / offshore",
        },
    ]


def find_template(name: str) -> dict[str, str] | None:
    """Retorna template pelo nome ou None."""
    for tpl in get_templates():
        if tpl["name"] == name:
            return tpl
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Matcher core
# ─────────────────────────────────────────────────────────────────────────────


def is_watch_active(watch: Watch, *, now: datetime | None = None) -> bool:
    """#289 — True se watch não expirou (expires_at)."""
    now = now or datetime.now(UTC)
    if watch.expires_at is None:
        return True
    expires = watch.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires > now


def is_in_cooldown(watch: Watch, *, now: datetime | None = None) -> bool:
    """#293 — True se watch está em cooldown (não pode disparar)."""
    if watch.cooldown_hours == 0 or watch.last_triggered is None:
        return False
    now = now or datetime.now(UTC)
    last = watch.last_triggered
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return now - last < timedelta(hours=watch.cooldown_hours)


def matches_doc(watch: Watch, doc: Documento) -> bool:  # noqa: PLR0911
    """Avalia se um documento corresponde ao pattern do watch.

    Considera tipo de pattern (term/regex/pl_number/uf_topic) + filtros
    (uf, relevancia_min). NÃO considera expiração/cooldown — usar helpers
    separados para cada um.
    """
    if doc.llm and doc.llm.relevancia < watch.relevancia_min:
        return False
    if watch.uf and doc.source.uf != watch.uf:
        return False

    if watch.pattern_type == "term":
        return _term_match(watch.pattern, doc)
    if watch.pattern_type == "regex":
        return _regex_match(watch.pattern, doc)
    if watch.pattern_type == "pl_number":
        return _pl_number_match(watch.pattern, doc)
    if watch.pattern_type == "uf_topic":
        return _uf_topic_match(watch.pattern, doc)
    return False


def _term_match(pattern: str, doc: Documento) -> bool:
    """#281 — match de termo simples (case-insensitive)."""
    pattern_lower = pattern.lower()
    haystack = doc.original.titulo_raw.lower()
    if doc.llm:
        haystack += " " + doc.llm.resumo.lower()
    # #287 — suporta AND/OR/NOT se o pattern tiver os operadores
    if any(op in pattern_lower for op in (" and ", " or ", " not ")):
        return _logical_term_match(pattern_lower, haystack)
    return pattern_lower in haystack


def _logical_term_match(pattern: str, haystack: str) -> bool:
    """#287 — avaliação local de AND/OR/NOT (sem parênteses)."""
    # Reusa boolean_search semantics em cima do haystack único
    # via decomposição manual
    result = boolean_search([_make_haystack_doc(haystack)], pattern, limit=1)
    return len(result) > 0


def _make_haystack_doc(haystack: str) -> Documento:
    """Cria doc sintético para reuso do boolean_search; só serve internamente."""
    from monitoritcd.core.models import (  # noqa: PLC0415
        Documento,
        Parser,
        RawItem,
        Source,
        TipoFonte,
    )

    raw = RawItem(
        source_id="watch-eval",
        titulo_raw=haystack[:500] or "x",
        url="https://example.com/",
        fetched_at=datetime.now(UTC),
        content_hash="0" * 64,
    )
    src = Source(
        id="watch-eval",
        uf="_federal",
        nome="x",
        tipo=TipoFonte.NOTICIA,
        parser=Parser.GENERIC_HTML,
        url="https://example.com/",
        keywords_required=[],
    )
    return Documento(owner_id="o", doc_id="watch-eval", source=src, original=raw, user_tags=[])


def _regex_match(pattern: str, doc: Documento) -> bool:
    """#286 — match de regex no titulo + resumo."""
    try:
        return len(regex_search([doc], pattern, limit=1)) > 0
    except ValueError:
        return False


def _pl_number_match(pattern: str, doc: Documento) -> bool:
    """#282 — match exato do número de PL/Lei (formato 'NUMERO/AAAA')."""
    # Pattern esperado: "1234/2026"
    extracted = doc.llm.metadados_extraidos.get("numero_ato") if doc.llm else None
    return extracted == pattern.strip()


def _uf_topic_match(pattern: str, doc: Documento) -> bool:
    """#283 — match composto 'UF:topico' (ex: 'SP:itcd')."""
    if ":" not in pattern:
        return False
    uf, _, topico = pattern.partition(":")
    if doc.source.uf != uf.strip():
        return False
    if not doc.llm:
        return False
    # Topico pode estar em llm.topics ou metadados.temas_especificos
    topico_norm = topico.strip().lower()
    # topics agora são strings (suporte a topics dinâmicos via /topicos)
    topics_doc = set(doc.llm.topics)
    if topico_norm in topics_doc:
        return True
    temas_csv = doc.llm.metadados_extraidos.get("temas_especificos", "").lower()
    return topico_norm in temas_csv.split(",")


# ─────────────────────────────────────────────────────────────────────────────
# Filtros adicionais (compostos com matches_doc)
# ─────────────────────────────────────────────────────────────────────────────


def matches_high_relevance(doc: Documento, *, min_score: int = 8) -> bool:
    """#291 — só dispara em relevância alta."""
    return doc.llm is not None and doc.llm.relevancia >= min_score


def matches_aliquota_change(doc: Documento) -> bool:
    """#299 — disparou se metadados contém aliquotas (mudança detectada)."""
    return bool(doc.llm and doc.llm.metadados_extraidos.get("aliquotas"))


def matches_revogacao(doc: Documento) -> bool:
    """#300 — disparou se metadados indica revogação."""
    return bool(doc.llm and doc.llm.metadados_extraidos.get("revogacoes_citadas"))


def matches_modulacao(doc: Documento) -> bool:
    """#301 — disparou se metadados indica modulação de efeitos."""
    return bool(doc.llm and doc.llm.metadados_extraidos.get("modulacao_efeitos") == "true")


def matches_tipo(doc: Documento, tipo: str) -> bool:
    """#298 — match por tipo de ato (decreto/sancao/etc)."""
    return doc.llm is not None and doc.llm.tipo.value == tipo


def matches_similar(
    doc: Documento, target_titulo: str, *, threshold: float = SIMILAR_HIGH_THRESHOLD
) -> bool:
    """#297 — disparou se titulo similar > threshold ao alvo."""
    ratio = SequenceMatcher(
        None,
        doc.original.titulo_raw.lower(),
        target_titulo.lower(),
    ).ratio()
    return ratio >= threshold


def matches_cluster(doc: Documento, cluster_id: str) -> bool:
    """#302 — match por cluster_id (mesmo tema)."""
    return doc.cluster_id == cluster_id


# ─────────────────────────────────────────────────────────────────────────────
# Avaliador completo
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_watches(
    docs: Sequence[Documento],
    watches: Sequence[Watch],
    *,
    now: datetime | None = None,
) -> list[tuple[Watch, Documento]]:
    """Para cada doc, retorna lista (watch, doc) que correspondem.

    Filtra watches expirados e em cooldown. Aplica matches_doc + filtros
    de alta relevância (se watch.relevancia_min >= 8).
    """
    matches: list[tuple[Watch, Documento]] = []
    for watch in watches:
        if not is_watch_active(watch, now=now):
            continue
        if is_in_cooldown(watch, now=now):
            continue
        matches.extend((watch, doc) for doc in docs if matches_doc(watch, doc))
    return matches


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzy convenience
# ─────────────────────────────────────────────────────────────────────────────


def fuzzy_watches_for_query(
    docs: Sequence[Documento],
    query: str,
    *,
    threshold: float = SIMILAR_HIGH_THRESHOLD,
) -> list[Documento]:
    """Helper para watches que usam fuzzy match contra um termo livre."""
    return [d for d, _ in fuzzy_search(docs, query, threshold=threshold)]


__all__ = [
    "DEFAULT_COOLDOWN_HOURS",
    "SIMILAR_HIGH_THRESHOLD",
    "evaluate_watches",
    "find_template",
    "fuzzy_watches_for_query",
    "get_templates",
    "is_in_cooldown",
    "is_watch_active",
    "matches_aliquota_change",
    "matches_cluster",
    "matches_doc",
    "matches_high_relevance",
    "matches_modulacao",
    "matches_revogacao",
    "matches_similar",
    "matches_tipo",
]
