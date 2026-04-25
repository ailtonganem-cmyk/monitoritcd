"""Notifiers: Email + Telegram com severity tiers e templates."""

from __future__ import annotations

from monitoritcd.notifiers.email_notifier import EmailNotifier
from monitoritcd.notifiers.severity import (
    channels_for_tier,
    digest_period,
    is_immediate,
)
from monitoritcd.notifiers.telegram_notifier import TelegramNotifier

__all__ = [
    "EmailNotifier",
    "TelegramNotifier",
    "channels_for_tier",
    "digest_period",
    "is_immediate",
]
