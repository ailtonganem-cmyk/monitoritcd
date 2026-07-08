"""Busca e navegação no corpus de documentos.

Cobre IDEAS.md Categoria 8 (#256-#280). Funções puras (operam em
Sequence[Documento]) — usar atrás de cache em memória ou storage layer.

Itens cobertos:
- #259 busca facetada (UF + tipo + data + relevância)
- #260 highlight de termos
- #261 normalização de número de ato
- #262 busca por órgão emissor (campo source.nome)
- #263 busca por relator (extraído via thematic_detector)
- #267 busca booleana AND/OR/NOT
- #268 fuzzy (Levenshtein via difflib)
- #269 busca temporal
- #275 busca por tag (user_tags)
- #276 busca por modelo LLM
- #277 busca por versão de prompt
- #278 "mais como este" (similaridade fuzzy de título)
- #270 export do resultado (helpers reaproveitam build_csv/json_attachment)
- #280 regex avançada

Itens pré-existentes (no bot handle_buscar):
- #258 cosine — TODO (requer embeddings, deps pesadas)
- #256 SQLite FTS5 — TODO (otimização futura)
- #257 semântica via sentence-transformers — TODO (heavy ML)
- #264-#266 favoritar/historico/autocomplete — UI/state
- #271-#274 — UX features
- #279 CLI — pode ser adicionado em main.py

Princípios canônicos:
- Princípio 1: query é input não confiável; sanitize via regex/limites
- Princípio 2: max query length, max results
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from monitoritcd.core import limits
from monitoritcd.core.models import DocumentSearchIndex

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import Documento

MAX_QUERY_LENGTH: Final[int] = 500
MAX_RESULTS: Final[int] = 100
DEFAULT_FUZZY_THRESHOLD: Final[float] = 0.7
SIMILAR_THRESHOLD: Final[float] = 0.5

# Mitigação ReDoS (Pentest 2026-04-26 V1 / Alta).
# Python `re` não tem timeout nativo. Padrões catastróficos como
# `(a+)+$` causam backtracking exponencial. Limites defensivos:
# - Pattern não pode ter quantificador aninhado óbvio.
# - Comprimento total do pattern bound em MAX_QUERY_LENGTH.
# - Aviso: para defesa estrita, considere lib externa `regex` com timeout.
RE_NESTED_QUANTIFIER: Final[re.Pattern[str]] = re.compile(
    r"\([^)]*[+*?]\)[+*?]"  # ex: (a+)+, (.*)*
)
MAX_REGEX_BACKREFS: Final[int] = 3

# #261 — Normalização de número de ato
RE_NUMERO_NORMALIZE: Final[re.Pattern[str]] = re.compile(
    r"(?:lei|decreto|portaria|resolu\w+|instru\w+|in)?\s*"
    r"(?:n[ºo°.]?\s*)?(\d{1,3}(?:\.\d{3})*|\d{1,5})\s*[/.,\s\-de]+\s*(\d{4})",
    re.IGNORECASE,
)

# #269 — Busca temporal: "30d", "última semana", "abril 2026", "Q1 2026"
RE_RELATIVO: Final[re.Pattern[str]] = re.compile(r"^(\d{1,3})([dwmy])$", re.IGNORECASE)
RE_MES_ANO: Final[re.Pattern[str]] = re.compile(
    r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\w*\s+(\d{4})",
    re.IGNORECASE,
)
RE_QUARTER: Final[re.Pattern[str]] = re.compile(r"^Q([1-4])\s+(\d{4})$", re.IGNORECASE)
RE_DATE_ISO: Final[re.Pattern[str]] = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")
RE_SEARCH_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"\d{1,6}/\d{4}|[\wÀ-ÿ]{3,}",
    re.IGNORECASE,
)
SEARCH_INDEX_VERSION: Final[int] = 2

MES_TO_NUM: Final[dict[str, int]] = {
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}


# ─────────────────────────────────────────────────────────────────────────────
# Validação e sanitização
# ─────────────────────────────────────────────────────────────────────────────


def _validate_query(query: str) -> str:
    """Princípio 1: query é input não confiável."""
    if not query or len(query) > MAX_QUERY_LENGTH:
        msg = f"Query inválida (vazia ou > {MAX_QUERY_LENGTH} chars)"
        raise ValueError(msg)
    return query.strip()


def _normalize_search_text(text: str) -> str:
    """Normaliza corpus de busca sem alterar o `original` armazenado."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = "".join(c for c in text if c.isprintable() or c.isspace())
    return " ".join(text.lower().split())


def normalize_search_query(text: str) -> str:
    """Normaliza termos de consulta com as mesmas regras do corpus."""
    return _normalize_search_text(text)


def search_terms_for_query(terms: Sequence[str]) -> list[str]:
    """Extrai candidatos compatíveis com `DocumentSearchIndex.terms`."""
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        normalized = normalize_search_query(term)
        if not normalized:
            continue
        candidates = [normalized]
        candidates.extend(m.group(0) for m in RE_SEARCH_TOKEN.finditer(normalized))
        for candidate in candidates:
            value = normalize_search_query(candidate)[: limits.MAX_SEARCH_TERM_LENGTH]
            if value and value not in seen:
                seen.add(value)
                out.append(value)
    return out


def build_document_search_text(doc: Documento) -> str:
    """Monta o corpus pesquisável de um documento.

    Inclui título, texto bruto, resumos, pontos-chave, metadados, tags, fonte,
    tópicos e marcações pessoais. O texto é derivado e limitado para caber no
    documento Firestore sem usar o `original` como índice bruto.
    """
    llm_parts: list[str] = []
    metadata_parts: list[str] = []
    if doc.llm:
        metadata_parts = [f"{k} {v}" for k, v in doc.llm.metadados_extraidos.items()]
        llm_parts = [
            doc.llm.tipo.value,
            doc.llm.severity_tier.value,
            doc.llm.resumo,
            doc.llm.resumo_completo,
            doc.llm.motivo_relevancia,
            doc.llm.contexto,
            " ".join(doc.llm.pontos_chave),
            " ".join(doc.llm.assuntos_relacionados),
            " ".join(doc.llm.tags),
            " ".join(doc.llm.topics),
            " ".join(metadata_parts),
        ]

    raw_excerpt = (doc.original.texto_raw or "")[: limits.MAX_RAW_TEXT_IN_SEARCH_INDEX_LENGTH]
    parts: list[str] = [
        doc.doc_id,
        doc.original.titulo_raw,
        doc.source.id,
        doc.source.nome,
        doc.source.uf,
        doc.source.tipo.value,
        " ".join(doc.source.topics),
        " ".join(doc.user_tags),
        *llm_parts,
        doc.original.url,
        raw_excerpt,
    ]
    if doc.original.data_publicacao:
        parts.append(doc.original.data_publicacao.isoformat())
    normalized = _normalize_search_text("\n".join(p for p in parts if p))
    return normalized[: limits.MAX_SEARCH_TEXT_LENGTH]


def _structured_terms(doc: Documento) -> list[str]:
    """Termos exatos importantes para buscas futuras e índices invertidos."""
    terms = [
        doc.doc_id,
        doc.source.id,
        doc.source.uf,
        doc.source.tipo.value,
        *doc.source.topics,
        *doc.user_tags,
    ]
    if doc.original.data_publicacao:
        terms.append(str(doc.original.data_publicacao.year))
    if doc.llm:
        terms.extend(
            [
                doc.llm.tipo.value,
                doc.llm.severity_tier.value,
                str(doc.llm.relevancia),
                *doc.llm.topics,
                *doc.llm.tags,
                *doc.llm.assuntos_relacionados,
            ]
        )
        for key, value in doc.llm.metadados_extraidos.items():
            terms.append(key)
            terms.append(value)
    return terms


def build_document_search_index(
    doc: Documento,
    *,
    generated_at: datetime | None = None,
) -> DocumentSearchIndex:
    """Gera índice materializado para persistir junto ao documento."""
    text = build_document_search_text(doc)
    seen: set[str] = set()
    terms: list[str] = []
    candidates = [*_structured_terms(doc), *(m.group(0) for m in RE_SEARCH_TOKEN.finditer(text))]
    for candidate in candidates:
        term = _normalize_search_text(candidate)[: limits.MAX_SEARCH_TERM_LENGTH]
        if not term:
            continue
        if term not in seen:
            seen.add(term)
            terms.append(term)
            if len(terms) >= limits.MAX_SEARCH_TERMS:
                break
    topics = doc.llm.topics if doc.llm and doc.llm.topics else list(doc.source.topics)
    return DocumentSearchIndex(
        index_version=SEARCH_INDEX_VERSION,
        generated_at=generated_at or datetime.now(UTC),
        text=text,
        terms=terms,
        topics=topics,
        prompt_version=doc.llm.llm_prompt_version if doc.llm else "",
    )


def document_search_corpus(doc: Documento) -> str:
    """Retorna corpus materializado ou gera fallback para documentos antigos."""
    if doc.search_index is not None and doc.search_index.text:
        return doc.search_index.text
    return build_document_search_text(doc)


def normalize_act_number(text: str) -> str | None:
    """#261 — Normaliza número de ato para forma canônica `NUMERO/AAAA`.

    Aceita variações: `Lei nº 1234/2026`, `Lei 1.234, de 2026`, `1234/2026`.
    """
    m = RE_NUMERO_NORMALIZE.search(text)
    if not m:
        return None
    numero = m.group(1).replace(".", "")
    return f"{numero}/{m.group(2)}"


# ─────────────────────────────────────────────────────────────────────────────
# Busca facetada
# ─────────────────────────────────────────────────────────────────────────────


def faceted_search(  # noqa: PLR0912
    docs: Sequence[Documento],
    *,
    term: str | None = None,
    uf: str | None = None,
    tipo: str | None = None,
    severity_tier: str | None = None,
    relevancia_min: int | None = None,
    period: str | None = None,
    tag: str | None = None,
    llm_model: str | None = None,
    prompt_version: str | None = None,
    limit: int = MAX_RESULTS,
) -> list[Documento]:
    """#259 — Busca com múltiplas facetas combinadas (AND).

    Args:
        docs: corpus.
        term: substring case-insensitive em titulo+resumo (#260)
        uf: UF exata.
        tipo: TipoAto value.
        severity_tier: SeverityTier value.
        relevancia_min: relevância >= N (#178).
        period: "30d", "abril 2026", "Q1 2026", "2026-04" (#269).
        tag: user_tag (#275).
        llm_model: modelo LLM usado (#276).
        prompt_version: versão de prompt (#277).
        limit: max resultados.
    """
    if term is not None:
        term = _validate_query(term).lower()

    cutoff = _parse_period(period) if period else None

    results: list[Documento] = []
    for d in docs:
        if uf and d.source.uf != uf:
            continue
        if d.llm is None:
            if any(
                x is not None
                for x in (tipo, severity_tier, relevancia_min, llm_model, prompt_version)
            ):
                continue
        else:
            if tipo and d.llm.tipo.value != tipo:
                continue
            if severity_tier and d.llm.severity_tier.value != severity_tier:
                continue
            if relevancia_min is not None and d.llm.relevancia < relevancia_min:
                continue
            if llm_model and d.llm.llm_model != llm_model:
                continue
            if prompt_version and d.llm.llm_prompt_version != prompt_version:
                continue
        if tag and tag not in d.user_tags:
            continue
        if term and not _contains_term(d, term):
            continue
        if cutoff:
            doc_dt = d.original.data_publicacao or d.original.fetched_at
            if doc_dt.tzinfo is None:
                doc_dt = doc_dt.replace(tzinfo=UTC)
            if doc_dt < cutoff:
                continue
        results.append(d)
        if len(results) >= limit:
            break
    return results


def _contains_term(doc: Documento, term: str) -> bool:
    """Procura substring no corpus pesquisável (case-insensitive)."""
    return _normalize_search_text(term) in document_search_corpus(doc)


def _parse_period(period: str) -> datetime | None:
    """#269 — converte string de período em datetime cutoff."""
    period = period.strip()
    now = datetime.now(UTC)

    # "30d", "1w", "6m", "1y"
    m = RE_RELATIVO.match(period)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days_map = {"d": 1, "w": 7, "m": 30, "y": 365}
        return now - timedelta(days=n * days_map[unit])

    # "abril 2026"
    m_mes = RE_MES_ANO.search(period.lower())
    if m_mes:
        mes = MES_TO_NUM[m_mes.group(1)[:3].lower()]
        ano = int(m_mes.group(2))
        return datetime(ano, mes, 1, tzinfo=UTC)

    # "Q1 2026"
    m_q = RE_QUARTER.match(period.upper())
    if m_q:
        q = int(m_q.group(1))
        ano = int(m_q.group(2))
        mes = (q - 1) * 3 + 1
        return datetime(ano, mes, 1, tzinfo=UTC)

    # "2026-04" ou "2026-04-15"
    m_iso = RE_DATE_ISO.match(period)
    if m_iso:
        ano = int(m_iso.group(1))
        mes = int(m_iso.group(2))
        dia = int(m_iso.group(3)) if m_iso.group(3) else 1
        return datetime(ano, mes, dia, tzinfo=UTC)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Busca booleana (#267)
# ─────────────────────────────────────────────────────────────────────────────


def boolean_search(
    docs: Sequence[Documento],
    expression: str,
    *,
    limit: int = MAX_RESULTS,
) -> list[Documento]:
    """#267 — Busca booleana AND / OR / NOT.

    Sintaxe simples (não suporta parênteses):
        - "ITCMD AND SP"
        - "alíquota OR progressiva"
        - "ITCD NOT veto"

    Default = AND entre tokens (igual ao Google).
    """
    expression = _validate_query(expression).lower()
    tokens = re.split(r"\s+(and|or|not)\s+", expression)
    if len(tokens) == 1:
        # AND implícito entre todas as palavras
        words = expression.split()
        return _and_filter(docs, words, limit)

    # Avaliação left-to-right
    op = "and"
    current_set: set[str] | None = None  # set de doc_ids
    by_id = {d.doc_id: d for d in docs}

    for tok in tokens:
        if tok in {"and", "or", "not"}:
            op = tok
            continue
        matching_ids = {d.doc_id for d in docs if _contains_term(d, tok)}
        if current_set is None:
            current_set = matching_ids
        elif op == "and":
            current_set &= matching_ids
        elif op == "or":
            current_set |= matching_ids
        elif op == "not":
            current_set -= matching_ids

    result_ids = list(current_set or set())[:limit]
    return [by_id[i] for i in result_ids if i in by_id]


def _and_filter(
    docs: Sequence[Documento],
    words: list[str],
    limit: int,
) -> list[Documento]:
    return [d for d in docs if all(_contains_term(d, w) for w in words)][:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzy (#268)
# ─────────────────────────────────────────────────────────────────────────────


def fuzzy_search(
    docs: Sequence[Documento],
    query: str,
    *,
    threshold: float = DEFAULT_FUZZY_THRESHOLD,
    limit: int = MAX_RESULTS,
) -> list[tuple[Documento, float]]:
    """#268 — Busca fuzzy via Levenshtein normalizado (SequenceMatcher).

    Returns:
        Lista de (doc, similarity) ordenada por similarity desc.
    """
    query = _validate_query(query).lower()
    matches: list[tuple[Documento, float]] = []
    for d in docs:
        haystack = d.original.titulo_raw.lower()
        ratio = SequenceMatcher(None, query, haystack).ratio()
        if ratio >= threshold:
            matches.append((d, ratio))
    matches.sort(key=lambda x: -x[1])
    return matches[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Highlights (#260)
# ─────────────────────────────────────────────────────────────────────────────


def highlight_term(text: str, term: str, *, mark: str = "**") -> str:
    """#260 — Envolve `term` em `mark` (default: bold MarkdownV2)."""
    if not term:
        return text
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    return pattern.sub(lambda m: f"{mark}{m.group(0)}{mark}", text)


# ─────────────────────────────────────────────────────────────────────────────
# Mais como este (#278)
# ─────────────────────────────────────────────────────────────────────────────


def more_like_this(
    target: Documento,
    docs: Sequence[Documento],
    *,
    threshold: float = SIMILAR_THRESHOLD,
    limit: int = 5,
) -> list[tuple[Documento, float]]:
    """#278 — Lista docs similares ao target (excluindo o próprio)."""
    title_target = target.original.titulo_raw.lower()
    matches: list[tuple[Documento, float]] = []
    for d in docs:
        if d.doc_id == target.doc_id:
            continue
        ratio = SequenceMatcher(None, title_target, d.original.titulo_raw.lower()).ratio()
        if ratio >= threshold:
            matches.append((d, ratio))
    matches.sort(key=lambda x: -x[1])
    return matches[:limit]


# ─────────────────────────────────────────────────────────────────────────────
# Regex avançada (#280)
# ─────────────────────────────────────────────────────────────────────────────


def _validate_regex_safety(pattern: str) -> None:
    """Pentest V1: rejeita padrões catastróficos antes da compilação.

    Bloqueia quantificadores aninhados (ex: `(a+)+`) e backreferences
    excessivas que costumam levar a ReDoS exponencial em `re`.
    """
    if RE_NESTED_QUANTIFIER.search(pattern):
        msg = "Regex insegura: quantificador aninhado (ex: '(a+)+'). Reescreva sem aninhamento."
        raise ValueError(msg)
    if pattern.count("\\1") + pattern.count("\\2") + pattern.count("\\3") > MAX_REGEX_BACKREFS:
        msg = f"Regex com mais de {MAX_REGEX_BACKREFS} backreferences (ReDoS risco)."
        raise ValueError(msg)


def regex_search(
    docs: Sequence[Documento],
    pattern: str,
    *,
    limit: int = MAX_RESULTS,
) -> list[Documento]:
    """#280 — Busca regex avançada (poweruser).

    Princípio 1: pattern compilado com timeout implícito (Python re não
    tem timeout nativo). Defesas contra ReDoS:
    - `_validate_regex_safety` rejeita quantificadores aninhados óbvios
    - `_validate_query` força MAX_QUERY_LENGTH
    - Search limit cap previne degradação prolongada
    """
    pattern = _validate_query(pattern)
    _validate_regex_safety(pattern)
    try:
        rgx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        msg = f"Regex inválida: {e}"
        raise ValueError(msg) from e

    matches: list[Documento] = []
    for d in docs:
        haystack = document_search_corpus(d)
        if rgx.search(haystack):
            matches.append(d)
            if len(matches) >= limit:
                break
    return matches


__all__ = [
    "DEFAULT_FUZZY_THRESHOLD",
    "MAX_QUERY_LENGTH",
    "MAX_RESULTS",
    "SIMILAR_THRESHOLD",
    "boolean_search",
    "build_document_search_index",
    "build_document_search_text",
    "document_search_corpus",
    "faceted_search",
    "fuzzy_search",
    "highlight_term",
    "more_like_this",
    "normalize_act_number",
    "normalize_search_query",
    "regex_search",
    "search_terms_for_query",
]
