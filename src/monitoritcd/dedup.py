"""Deduplicação em camadas.

Estratégias (do mais forte ao mais fraco):
1. **Hash do conteúdo**: igual = mesmo item. (forte)
2. **URL canônica**: mesmo URL no mesmo dia = mesmo item. (forte)
3. **Numero ato + UF**: extraído do título via regex. (média)
4. **Similaridade fuzzy**: Levenshtein normalizado ≥ 0.85. (fraca)

Atribui `cluster_id` (= hash do primeiro item do cluster) para agrupar
variações cobertas por fontes diferentes.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from monitoritcd.core import limits

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import RawItem

# Regex para extrair "número/ano" de títulos (ex: "Lei nº 1234/2026")
NUMERO_ATO_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?:nº|n\.|n°|num\.|número)?\s*(\d{1,5})[/.](\d{4})",
    re.IGNORECASE,
)

# Limiar de similaridade fuzzy
FUZZY_THRESHOLD: Final[float] = 0.85


def _normalize_for_compare(text: str) -> str:
    """Normaliza para comparação: NFKC + lower + remove pontuação leve + collapse spaces."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s/]", " ", text)
    return " ".join(text.split())


def _extract_numero_ato(titulo: str) -> str | None:
    """Extrai 'numero/ano' do título, ou None se não encontrar."""
    match = NUMERO_ATO_REGEX.search(titulo)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None


def _cluster_key(item: RawItem) -> str:
    """Gera chave determinística para clusterização (níveis 1+2+3)."""
    numero = _extract_numero_ato(item.titulo_raw)
    if numero:
        # Inclui source.uf seria ideal, mas RawItem não tem UF direta;
        # usamos source_id como proxy estável.
        return f"numato:{numero}"
    return f"url:{item.url}"


def _fuzzy_similarity(a: str, b: str) -> float:
    """Similaridade Levenshtein normalizada (SequenceMatcher.ratio)."""
    return SequenceMatcher(None, _normalize_for_compare(a), _normalize_for_compare(b)).ratio()


def _hash_id(values: list[str]) -> str:
    """SHA-256 hex curto (16 chars) para uso como cluster_id."""
    joined = "|".join(values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def assign_clusters(items: Sequence[RawItem]) -> dict[str, str]:
    """Atribui cluster_id a cada item.

    Args:
        items: itens a clusterizar (de uma execução, opcionalmente cross-source).

    Returns:
        Dict mapping `item.content_hash` → `cluster_id`.

    Cada cluster_id é estável: itens semanticamente equivalentes recebem o mesmo.
    """
    if not items:
        return {}
    if len(items) > limits.MAX_BATCH_LLM * 100:  # sanity
        msg = f"assign_clusters: lote muito grande ({len(items)})"
        raise ValueError(msg)

    cluster_by_key: dict[str, str] = {}  # cluster_key → cluster_id
    cluster_by_hash: dict[str, str] = {}  # content_hash → cluster_id
    title_index: list[tuple[str, str]] = []  # (titulo_normalizado, cluster_id) para fuzzy

    for item in items:
        # Camada 1: content_hash exato
        if item.content_hash in cluster_by_hash:
            continue

        # Camada 2: cluster key (URL ou número/ano)
        key = _cluster_key(item)
        if key in cluster_by_key:
            cluster_id = cluster_by_key[key]
        else:
            # Camada 3: similaridade fuzzy contra clusters existentes
            fuzzy_match = _find_fuzzy_cluster(item.titulo_raw, title_index)
            cluster_id = (
                fuzzy_match if fuzzy_match is not None else _hash_id([item.content_hash, key])
            )
            cluster_by_key[key] = cluster_id

        cluster_by_hash[item.content_hash] = cluster_id
        title_index.append((_normalize_for_compare(item.titulo_raw), cluster_id))

    return cluster_by_hash


def _find_fuzzy_cluster(
    titulo: str,
    title_index: list[tuple[str, str]],
) -> str | None:
    """Procura cluster existente com título similar (≥ FUZZY_THRESHOLD)."""
    titulo_norm = _normalize_for_compare(titulo)
    for indexed_title, cluster_id in title_index:
        ratio = SequenceMatcher(None, titulo_norm, indexed_title).ratio()
        if ratio >= FUZZY_THRESHOLD:
            return cluster_id
    return None


def is_duplicate(
    item: RawItem,
    seen_hashes: set[str],
    seen_keys: set[str] | None = None,
) -> bool:
    """Verifica se item é duplicata de algo já visto.

    Args:
        item: item a verificar.
        seen_hashes: set de content_hashes já vistos.
        seen_keys: opcional set de cluster_keys (URL ou numero/ano) já vistos.

    Returns:
        True se duplicata exata (hash) ou semantica (key).
    """
    if item.content_hash in seen_hashes:
        return True
    return seen_keys is not None and _cluster_key(item) in seen_keys
