"""Coletores de fontes (RSS, HTML, LexML, custom)."""

from __future__ import annotations

from monitoritcd.collectors.custom.alep import ALEPCollector
from monitoritcd.collectors.custom.almg import ALMGCollector
from monitoritcd.collectors.custom.lexml_portal import LexMLPortalCollector
from monitoritcd.collectors.custom.sapl import SAPLCollector
from monitoritcd.collectors.generic_html import GenericHTMLCollector
from monitoritcd.collectors.generic_rss import GenericRSSCollector
from monitoritcd.collectors.lexml import LexMLCollector

__all__ = [
    "ALEPCollector",
    "ALMGCollector",
    "GenericHTMLCollector",
    "GenericRSSCollector",
    "LexMLCollector",
    "LexMLPortalCollector",
    "SAPLCollector",
]
