"""Filtro 1 — keywords.

Antes de pagar custo de LLM, filtramos itens que não contenham nenhuma
das keywords das divisões temáticas do sistema. Comparação case-insensitive
e Unicode-NFKC-normalizada (defesa contra homoglyph).

Divisões temáticas (`Topic`):
- ITCD: tributário (alíquotas, IN, portarias).
- SUCESSOES: Direito Civil — herança, testamento, inventário (CC 1.784+).
- REGIME_BENS: regimes matrimoniais (CC 1.639-1.688).

Cada divisão tem um conjunto de keywords. `KEYWORDS_DEFAULT` é a UNIÃO de todas
(comportamento legado mantido para backward compat).
"""

from __future__ import annotations

import unicodedata
from typing import Final

from monitoritcd.core.models import Topic

# ─────────────────────────────────────────────────────────────────────────────
# ITCD — tributário (mantido como divisão original)
# ─────────────────────────────────────────────────────────────────────────────
KEYWORDS_ITCD: Final[tuple[str, ...]] = (
    # Tributo (todas as variações)
    "ITCMD",
    "ITCD",
    "ITD",
    # Causa mortis
    "causa mortis",
    "causa-mortis",
    "causa  mortis",  # tolerância a espaço duplo
    # Sucessão / inventário
    "inventário",
    "inventario",
    "espólio",
    "espolio",
    "sucessão",
    "sucessao",
    "partilha",
    "partilhar",
    "partilhamento",
    # Doação fiscal
    "doação",
    "doacao",
    # Planejamento
    "holding familiar",
    "planejamento sucessório",
    "planejamento sucessorio",
    "planejamento patrimonial",
    # Atos relacionados
    "transmissão causa mortis",
    "transmissao causa mortis",
    "transmissão por doação",
    # Aspectos técnicos
    "fato gerador",
    "base de cálculo",
    "base de calculo",
    "alíquota",
    "aliquota",
    # Normativos
    "GIA-ITCMD",
    "GIA ITCMD",
    "DIME-D",
)


# ─────────────────────────────────────────────────────────────────────────────
# SUCESSOES — Direito Civil das Sucessões (CC 1.784+)
# ─────────────────────────────────────────────────────────────────────────────
KEYWORDS_SUCESSOES: Final[tuple[str, ...]] = (
    # Estrutura geral
    "direito sucessório",
    "direito das sucessões",
    "sucessão hereditária",
    "abertura da sucessão",
    "saisine",
    # Herdeiros
    "herdeiros",
    "herdeiro necessário",
    "herdeiros necessários",
    "herdeiros legítimos",
    "herdeiro testamentário",
    "legítima",
    "quota legitimária",
    "legitimários",
    # Inventário e partilha
    "inventário judicial",
    "inventário extrajudicial",
    "arrolamento",
    "partilha amigável",
    "partilha judicial",
    "sobrepartilha",
    "Provimento 56",
    # Testamento
    "testamento",
    "testamento público",
    "testamento particular",
    "testamento cerrado",
    "testamento conjuntivo",
    "codicilo",
    "deserdação",
    "indignidade",
    # Cônjuge/companheiro
    "cônjuge supérstite",
    "companheiro supérstite",
    "meação",
    "usufruto vidual",
    # União estável
    "união estável",
    "art. 1.829",
    "art 1829",
    # Renúncia/aceitação
    "renúncia da herança",
    "cessão de direitos hereditários",
    "aceitação da herança",
    "colação",
    "sonegados",
    "redução de liberalidade",
    # Específicos
    "petição de herança",
    "ação de inventário",
    "alvará judicial",
    "doação inoficiosa",
)

# ─────────────────────────────────────────────────────────────────────────────
# REGIME_BENS — Regime de Bens (CC 1.639-1.688)
# ─────────────────────────────────────────────────────────────────────────────
KEYWORDS_REGIME_BENS: Final[tuple[str, ...]] = (
    # Regimes
    "regime de bens",
    "regimes de bens",
    "comunhão parcial",
    "comunhão parcial de bens",
    "comunhão universal",
    "comunhão universal de bens",
    "separação total",
    "separação total de bens",
    "separação obrigatória",
    "separação obrigatória de bens",
    "separação convencional",
    "separação legal",
    "participação final nos aquestos",
    "aquestos",
    # Pacto antenupcial
    "pacto antenupcial",
    "convenção antenupcial",
    "alteração de regime",
    "modificação de regime",
    # Súmulas e marcos
    "Súmula 377",
    "súmula 377",
    "art. 1.639",
    "art. 1.640",
    "art. 1.641",
    "art. 1.658",
    "art. 1.667",
    "art. 1.687",
    # Patrimônio conjugal
    "bens comuns",
    "bens particulares",
    "bens reservados",
    "patrimônio comum",
    # Aplicações práticas
    "divórcio com partilha",
    "divórcio extrajudicial",
    "dissolução da sociedade conjugal",
    "casamento idoso",
    "casamento septuagenário",
)


# ─────────────────────────────────────────────────────────────────────────────
# Mapeamento Topic → keywords
# ─────────────────────────────────────────────────────────────────────────────
KEYWORDS_BY_TOPIC: Final[dict[Topic, tuple[str, ...]]] = {
    Topic.ITCD: KEYWORDS_ITCD,
    Topic.SUCESSOES: KEYWORDS_SUCESSOES,
    Topic.REGIME_BENS: KEYWORDS_REGIME_BENS,
}

# União de todas — mantém compatibilidade com código legado (`KEYWORDS_DEFAULT`)
KEYWORDS_DEFAULT: Final[tuple[str, ...]] = tuple(
    sorted({*KEYWORDS_ITCD, *KEYWORDS_SUCESSOES, *KEYWORDS_REGIME_BENS})
)


def _normalize(text: str) -> str:
    """Normalização para comparação: NFKC + lower + collapse whitespace."""
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join(text.split())


def matches_keywords(
    text: str,
    keywords: tuple[str, ...] | list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Retorna (matched, lista de keywords encontradas no texto).

    Args:
        text: texto a verificar (título, resumo, conteúdo).
        keywords: lista customizada. Se None, usa `KEYWORDS_DEFAULT` (união de todos os tópicos).

    Returns:
        Tupla (bool, list[str]):
            - bool: True se ≥ 1 keyword encontrada.
            - list[str]: keywords encontradas (originais, não normalizadas).
    """
    if not text:
        return False, []

    kws = keywords if keywords is not None else KEYWORDS_DEFAULT
    text_norm = _normalize(text)
    found = [kw for kw in kws if _normalize(kw) in text_norm]
    return bool(found), found


def detect_topics(text: str) -> list[Topic]:
    """Detecta tópicos do texto baseado em densidade de keywords.

    Útil para classificação preliminar sem LLM. Um texto pode pertencer a
    múltiplos tópicos (ex: ITCD progressivo em SP toca os 3 simultaneamente).

    Returns:
        Lista de tópicos com ≥ 1 keyword no texto, em ordem de preponderância.
    """
    if not text:
        return []
    text_norm = _normalize(text)
    scores: dict[Topic, int] = {}
    for topic, kws in KEYWORDS_BY_TOPIC.items():
        count = sum(1 for kw in kws if _normalize(kw) in text_norm)
        if count > 0:
            scores[topic] = count
    return [t for t, _ in sorted(scores.items(), key=lambda x: -x[1])]
