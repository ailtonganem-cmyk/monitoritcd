"""Validação de citações de artigos do CC (Sugestão #49).

Pós-processamento que verifica citações como "art. 1.829 do CC" contra
um dicionário estático de artigos conhecidos. Marca `citation_invalid`
para revisão sem invalidar o documento.
"""

from __future__ import annotations

import re
from typing import Final

# Faixas válidas de artigos do Código Civil de 2002 (Lei 10.406/2002).
# Não exaustivo, mas cobre os blocos relevantes para sucessões/regime de bens.
CC_ART_RANGES: Final[list[tuple[int, int, str]]] = [
    (1, 232, "Parte Geral"),
    (233, 420, "Direito das Obrigações — Modalidades"),
    (421, 853, "Direito das Obrigações — Contratos"),
    (854, 965, "Atos Unilaterais e Títulos de Crédito"),
    (966, 1195, "Direito de Empresa"),
    (1196, 1510, "Direito das Coisas"),
    (1511, 1638, "Direito de Família"),
    (1639, 1688, "Regime de Bens"),
    (1689, 1722, "Direito de Família — diversos"),
    (1723, 1727, "União Estável"),
    (1728, 1783, "Tutela e Curatela"),
    (1784, 1856, "Direito das Sucessões — disposições gerais"),
    (1857, 1990, "Sucessão Testamentária"),
    (1991, 2046, "Inventário e Partilha"),
    (2047, 2046, "Disposições Finais"),  # placeholder
]

# Captura "art. 1.234" ou "artigo 1234" — apenas dígitos com pontos opcionais
RE_CC_CITATION: Final = re.compile(
    r"\b(?:art(?:igo|\.|s?\.)?\s*)?(\d{1,4}(?:\.\d{3})?)\b(?:\s*-?\s*([A-Z]))?",
    re.IGNORECASE,
)


def is_valid_cc_article(num: int) -> bool:
    """True se `num` está em alguma faixa válida do CC."""
    if num < 1 or num > 2046:  # noqa: PLR2004
        return False
    return any(start <= num <= end for start, end, _ in CC_ART_RANGES)


def validate_cc_citations(text: str) -> tuple[bool, list[int]]:
    """Verifica todas as citações de artigos do CC no texto.

    Args:
        text: texto com possíveis citações.

    Returns:
        (todas_validas, lista_invalidas)
    """
    if not text:
        return True, []

    # Apenas busca em contexto explícito de CC para reduzir falso positivo
    cc_context = re.compile(
        r"(?:Código\s+Civil|CC)\b.{0,200}|.{0,200}\b(?:Código\s+Civil|CC)\b",
        re.IGNORECASE,
    )
    invalid: list[int] = []

    for match in cc_context.finditer(text):
        chunk = match.group(0)
        for cite in RE_CC_CITATION.finditer(chunk):
            num_str = cite.group(1).replace(".", "")
            try:
                num = int(num_str)
            except ValueError:
                continue
            # Heurística: ignora números muito pequenos (provavelmente não são
            # artigos do CC mas sim ano, item, etc.)
            if num < 100 and "art" not in chunk.lower():  # noqa: PLR2004
                continue
            if not is_valid_cc_article(num) and num not in invalid:
                invalid.append(num)

    return len(invalid) == 0, invalid
