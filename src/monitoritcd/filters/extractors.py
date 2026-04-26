"""Extração determinística de metadados antes do LLM (Sugestão #48).

Padrões regulares brasileiros (Lei nº X/AAAA, Decreto X, IN RFB X, etc.)
são extraídos via regex ANTES do LLM. Reduz alucinação e economiza tokens.

Princípio canônico do CLAUDE.md §5: LLM não modifica dados originais.
Esta camada é determinística e auditável; LLM apenas confirma ou complementa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# ─────────────────────────────────────────────────────────────────────────────
# Padrões de número de ato (variantes brasileiras)
# ─────────────────────────────────────────────────────────────────────────────

# "Lei nº 1.234/2026" ou "Lei n° 12345/2026" ou "Lei 1234/2026"
RE_LEI: Final = re.compile(
    r"\b(?:Lei|LEI)\s*(?:n[º°.]?\s*)?(\d{1,5}(?:\.\d{3})?)\s*[/\-]\s*(\d{4})\b",
    re.IGNORECASE,
)

# "Decreto nº 5.678/2025"
RE_DECRETO: Final = re.compile(
    r"\b(?:Decreto|DECRETO)\s*(?:n[º°.]?\s*)?(\d{1,6}(?:\.\d{3})?)\s*[/\-]\s*(\d{4})\b",
    re.IGNORECASE,
)

# "Instrução Normativa RFB nº 2.123/2026" ou "IN 2123/2026"
RE_IN: Final = re.compile(
    r"\b(?:Instrução\s+Normativa|IN)\s*(?:RFB|SRF|SRFB|SECEX)?\s*(?:n[º°.]?\s*)?"
    r"(\d{1,6}(?:\.\d{3})?)\s*[/\-]\s*(\d{4})\b",
    re.IGNORECASE,
)

# "Portaria nº 123/2026"
RE_PORTARIA: Final = re.compile(
    r"\b(?:Portaria|PORTARIA)\s*(?:n[º°.]?\s*)?(\d{1,6}(?:\.\d{3})?)\s*[/\-]\s*(\d{4})\b",
    re.IGNORECASE,
)

# "Provimento 56/CNJ" ou "Provimento nº 149/2023 do CNJ"
RE_PROVIMENTO: Final = re.compile(
    r"\bProvimento\s*(?:n[º°.]?\s*)?(\d{1,5})\s*[/\-]?\s*(?:CNJ|CGJ|(\d{4}))",
    re.IGNORECASE,
)

# Órgãos emissores (sigla → nome canônico)
ORGAOS_KNOWN: Final[dict[str, str]] = {
    "STF": "Supremo Tribunal Federal",
    "STJ": "Superior Tribunal de Justiça",
    "RFB": "Receita Federal do Brasil",
    "SRF": "Receita Federal",
    "PGFN": "Procuradoria-Geral da Fazenda Nacional",
    "AGU": "Advocacia-Geral da União",
    "CNJ": "Conselho Nacional de Justiça",
    "TIT-SP": "Tribunal de Impostos e Taxas de São Paulo",
    "SEFAZ-SP": "Secretaria da Fazenda de São Paulo",
    "SEFAZ-RJ": "Secretaria da Fazenda do Rio de Janeiro",
    "SEFAZ-MG": "Secretaria da Fazenda de Minas Gerais",
    "SEFAZ-RS": "Secretaria da Fazenda do Rio Grande do Sul",
    "SEFAZ-DF": "Secretaria da Fazenda do Distrito Federal",
}


@dataclass(frozen=True)
class ExtractedMetadata:
    """Metadados extraídos deterministicamente."""

    numero_ato: str | None = None
    tipo_ato: str | None = None
    ano: int | None = None
    orgao_emissor: str | None = None


def normalize_number(num: str) -> str:
    """Remove pontos de milhar: '1.234' → '1234'."""
    return num.replace(".", "")


def extract_ato(text: str) -> ExtractedMetadata:
    """Extrai número do ato e tipo do texto.

    Retorna primeira ocorrência. Se múltiplos atos no texto, o LLM resolve.
    """
    if not text:
        return ExtractedMetadata()

    # Ordem importa: padrões mais específicos primeiro
    for tipo, regex in (
        ("instrucao_normativa", RE_IN),
        ("provimento", RE_PROVIMENTO),
        ("decreto", RE_DECRETO),
        ("portaria", RE_PORTARIA),
        ("lei", RE_LEI),
    ):
        m = regex.search(text)
        if m:
            num = normalize_number(m.group(1))
            ano = m.group(2) if m.lastindex and m.lastindex >= 2 else None  # noqa: PLR2004
            try:
                ano_int = int(ano) if ano and ano.isdigit() else None
            except ValueError:
                ano_int = None
            numero_ato = f"{num}/{ano}" if ano else num
            return ExtractedMetadata(
                numero_ato=numero_ato,
                tipo_ato=tipo,
                ano=ano_int,
            )
    return ExtractedMetadata()


def extract_orgao(text: str) -> str | None:
    """Detecta órgão emissor por sigla conhecida."""
    if not text:
        return None
    upper = text.upper()
    for sigla in ORGAOS_KNOWN:
        # Limites de palavra para evitar falsos (ex: "STJ" em "ABCSTJ")
        pattern = r"\b" + re.escape(sigla) + r"\b"
        if re.search(pattern, upper):
            return sigla
    return None


def extract_all(text: str) -> ExtractedMetadata:
    """Combina extração de ato + órgão."""
    base = extract_ato(text)
    orgao = extract_orgao(text)
    if orgao and not base.orgao_emissor:
        return ExtractedMetadata(
            numero_ato=base.numero_ato,
            tipo_ato=base.tipo_ato,
            ano=base.ano,
            orgao_emissor=orgao,
        )
    return base
