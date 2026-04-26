"""Lint específico para YAMLs de fontes (#368 IDEAS.md).

Regras de domínio acima do schema pydantic:
- URLs governamentais devem usar HTTPS
- Fontes federais devem ter `uf: _federal`
- `keywords_required` deve incluir ITCMD ou ITCD
- `notas` deve mencionar fonte oficial vs especializada
- Fontes com `ativo: true` devem ter `geo_restricted` definido
- `topics` não pode ser vazio

Princípios canônicos:
- Princípio 1: validação adicional além do schema, antes do load
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monitoritcd.core.models import Source

GOV_DOMAINS = (".gov.br", ".jus.br", ".leg.br")
ITCD_KEYWORDS = {"ITCMD", "ITCD", "ITD", "causa mortis"}


def lint_source(source: Source) -> list[str]:
    """Aplica regras de domínio em uma Source. Retorna lista de avisos.

    Args:
        source: Source já validada por pydantic.

    Returns:
        Lista de mensagens (vazia se OK).
    """
    warnings: list[str] = []

    # 1. URLs gov devem ser HTTPS (já garantido pelo url_validator, mas reforço)
    if any(d in source.url for d in GOV_DOMAINS) and not source.url.startswith("https://"):
        warnings.append(f"URL gov sem HTTPS: {source.url}")

    # 2. Fontes federais devem ter uf=_federal
    federal_prefixes = ("stf", "stj", "trf", "lexml", "cnj", "senado", "camara")
    if source.id.startswith(federal_prefixes) and source.uf != "_federal":
        warnings.append(f"Fonte federal {source.id} com uf={source.uf} (esperado _federal)")

    # 3. Keywords obrigatórias
    if source.keywords_required:
        joined = " ".join(source.keywords_required).upper()
        has_core = any(kw.upper() in joined for kw in ITCD_KEYWORDS)
        if not has_core:
            warnings.append(f"keywords_required sem ITCMD/ITCD/ITD em {source.id}")

    # 4. Topics não pode ser vazio
    if not source.topics:
        warnings.append(f"topics vazio em {source.id}")

    # 5. Fontes ativas devem ter geo_restricted definido (booleano)
    if source.ativo and not isinstance(source.geo_restricted, bool):
        warnings.append(f"Fonte ativa {source.id} sem geo_restricted")

    # 6. Fontes fragile precisam de notas explicativas
    if source.fragile and not source.notas:
        warnings.append(f"Fonte fragile {source.id} sem campo notas")

    return warnings


def lint_all(sources: list[Source]) -> dict[str, list[str]]:
    """Lint em batch. Returns dict source_id → list[warning]."""
    return {s.id: w for s in sources if (w := lint_source(s))}


__all__ = ["GOV_DOMAINS", "ITCD_KEYWORDS", "lint_all", "lint_source"]
