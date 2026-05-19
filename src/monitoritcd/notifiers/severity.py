"""Roteamento por severity tier — quem notifica quando.

Decide canais e urgência baseado em `SeverityTier`:

| Tier        | Canais          | Urgência         | Período     |
|-------------|-----------------|------------------|-------------|
| CRITICO 🔴  | Telegram        | Push imediato    | Imediato    |
| ALTA 🟠     | Email+Telegram  | Em destaque      | Diário      |
| NORMAL 🟡   | Email+Telegram  | Normal           | Diário      |
| BAIXA 🟢    | Email           | —                | Semanal     |
| DESCARTADO  | (nenhum)        | —                | —           |

Também expõe `effective_severity(source, llm_result)` para aplicar overrides
baseados na configuração da fonte (ex: rebaixar NORMAL→BAIXA em fontes com
`keywords_bypass=True` para não poluir o Telegram com atos administrativos).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from monitoritcd.core.models import SeverityTier

if TYPE_CHECKING:
    from monitoritcd.core.models import LLMResult, Source

Channel = Literal["email", "telegram", "discord", "ntfy"]
DigestPeriod = Literal["immediate", "daily", "weekly", "none"]


def channels_for_tier(tier: SeverityTier) -> list[Channel]:
    """Retorna canais ativos para a tier."""
    if tier == SeverityTier.CRITICO:
        return ["telegram"]
    if tier in (SeverityTier.ALTA, SeverityTier.NORMAL):
        return ["email", "telegram"]
    if tier == SeverityTier.BAIXA:
        return ["email"]
    return []


def is_immediate(tier: SeverityTier) -> bool:
    """True se a tier requer push imediato (não pode esperar digest)."""
    return tier == SeverityTier.CRITICO


def digest_period(tier: SeverityTier) -> DigestPeriod:
    """Retorna o período de digest apropriado."""
    if tier == SeverityTier.CRITICO:
        return "immediate"
    if tier in (SeverityTier.ALTA, SeverityTier.NORMAL):
        return "daily"
    if tier == SeverityTier.BAIXA:
        return "weekly"
    return "none"


def emoji_for_tier(tier: SeverityTier) -> str:
    """Emoji associado à tier (visual nos notifiers)."""
    return {
        SeverityTier.CRITICO: "🔴",
        SeverityTier.ALTA: "🟠",
        SeverityTier.NORMAL: "🟡",
        SeverityTier.BAIXA: "🟢",
        SeverityTier.DESCARTADO: "⚪",
    }[tier]


def label_for_tier(tier: SeverityTier) -> str:
    """Label PT-BR para exibição."""
    return {
        SeverityTier.CRITICO: "Crítico",
        SeverityTier.ALTA: "Alta",
        SeverityTier.NORMAL: "Normal",
        SeverityTier.BAIXA: "Baixa",
        SeverityTier.DESCARTADO: "Descartado",
    }[tier]


def effective_severity(source: Source, llm_result: LLMResult) -> SeverityTier:
    """Calcula tier efetiva aplicando overrides por configuração da fonte.

    Regra atual (única override):
        Fontes com `keywords_bypass=True` entram itens via menção a órgão
        (org_mentions). O LLM classifica esses itens olhando para o conteúdo,
        mas atos administrativos rotineiros (nomeações, designações) podem
        receber NORMAL por estarem em fonte oficial. Para não poluir o canal
        diário do Telegram com esse tipo de ato, rebaixamos NORMAL→BAIXA
        nessas fontes.

        ALTA e CRITICO permanecem — se o LLM marcou esse tier, é algo
        substantivo (mudança de alíquota, decreto regulamentar) e merece
        push imediato/destaque mesmo vindo de fonte com bypass.

        DESCARTADO/BAIXA permanecem — já não estão no canal diário.

    Resumo da tabela:

    | source.keywords_bypass | llm_tier  | effective_tier |
    |------------------------|-----------|----------------|
    | False (qualquer fonte) | qualquer  | llm_tier       |
    | True                   | CRITICO   | CRITICO        |
    | True                   | ALTA      | ALTA           |
    | True                   | NORMAL    | **BAIXA**      |
    | True                   | BAIXA     | BAIXA          |
    | True                   | DESCARTADO| DESCARTADO     |

    Args:
        source: configuração da fonte que originou o item.
        llm_result: resultado da classificação LLM (imutável).

    Returns:
        SeverityTier ajustado. Pode ser igual a `llm_result.severity_tier`.
    """
    if source.keywords_bypass and llm_result.severity_tier == SeverityTier.NORMAL:
        return SeverityTier.BAIXA
    return llm_result.severity_tier
