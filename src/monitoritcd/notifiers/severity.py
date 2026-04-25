"""Roteamento por severity tier — quem notifica quando.

Decide canais e urgência baseado em `SeverityTier`:

| Tier        | Canais          | Urgência         | Período     |
|-------------|-----------------|------------------|-------------|
| CRITICO 🔴  | Telegram        | Push imediato    | Imediato    |
| ALTA 🟠     | Email+Telegram  | Em destaque      | Diário      |
| NORMAL 🟡   | Email+Telegram  | Normal           | Diário      |
| BAIXA 🟢    | Email           | —                | Semanal     |
| DESCARTADO  | (nenhum)        | —                | —           |
"""

from __future__ import annotations

from typing import Literal

from monitoritcd.core.models import SeverityTier

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
