"""Testes do roteamento por severity tier."""

from __future__ import annotations

import pytest

from monitoritcd.core.models import SeverityTier
from monitoritcd.notifiers.severity import (
    channels_for_tier,
    digest_period,
    emoji_for_tier,
    is_immediate,
    label_for_tier,
)


@pytest.mark.unit
class TestChannelsForTier:
    def test_critico_only_telegram(self) -> None:
        assert channels_for_tier(SeverityTier.CRITICO) == ["telegram"]

    def test_alta_email_and_telegram(self) -> None:
        assert sorted(channels_for_tier(SeverityTier.ALTA)) == ["email", "telegram"]

    def test_normal_email_and_telegram(self) -> None:
        assert sorted(channels_for_tier(SeverityTier.NORMAL)) == ["email", "telegram"]

    def test_baixa_email_only(self) -> None:
        assert channels_for_tier(SeverityTier.BAIXA) == ["email"]

    def test_descartado_no_channel(self) -> None:
        assert channels_for_tier(SeverityTier.DESCARTADO) == []


@pytest.mark.unit
class TestImmediate:
    def test_critico_is_immediate(self) -> None:
        assert is_immediate(SeverityTier.CRITICO) is True

    def test_alta_not_immediate(self) -> None:
        assert is_immediate(SeverityTier.ALTA) is False

    def test_descartado_not_immediate(self) -> None:
        assert is_immediate(SeverityTier.DESCARTADO) is False


@pytest.mark.unit
class TestDigestPeriod:
    def test_critico_immediate(self) -> None:
        assert digest_period(SeverityTier.CRITICO) == "immediate"

    def test_alta_daily(self) -> None:
        assert digest_period(SeverityTier.ALTA) == "daily"

    def test_normal_daily(self) -> None:
        assert digest_period(SeverityTier.NORMAL) == "daily"

    def test_baixa_weekly(self) -> None:
        assert digest_period(SeverityTier.BAIXA) == "weekly"

    def test_descartado_none(self) -> None:
        assert digest_period(SeverityTier.DESCARTADO) == "none"


@pytest.mark.unit
class TestEmojisAndLabels:
    @pytest.mark.parametrize("tier", list(SeverityTier))
    def test_emoji_returned_for_each_tier(self, tier: SeverityTier) -> None:
        assert emoji_for_tier(tier)

    @pytest.mark.parametrize("tier", list(SeverityTier))
    def test_label_returned_for_each_tier(self, tier: SeverityTier) -> None:
        assert label_for_tier(tier)

    def test_critico_emoji_red_circle(self) -> None:
        assert emoji_for_tier(SeverityTier.CRITICO) == "🔴"
