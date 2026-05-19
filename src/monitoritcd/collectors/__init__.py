"""Coletores de fontes (RSS, HTML, LexML, custom)."""

from __future__ import annotations

from monitoritcd.collectors.custom.alep import ALEPCollector
from monitoritcd.collectors.custom.alepe import ALEPECollector
from monitoritcd.collectors.custom.alesp import ALESPCollector
from monitoritcd.collectors.custom.almg import ALMGCollector
from monitoritcd.collectors.custom.camara_deputados import CamaraDeputadosCollector
from monitoritcd.collectors.custom.iof_mg import IOFMGCollector
from monitoritcd.collectors.custom.lexml_portal import LexMLPortalCollector
from monitoritcd.collectors.custom.sapl import SAPLCollector
from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector
from monitoritcd.collectors.custom.senado import SenadoCollector
from monitoritcd.collectors.generic_html import GenericHTMLCollector
from monitoritcd.collectors.generic_rss import GenericRSSCollector
from monitoritcd.collectors.lexml import LexMLCollector

__all__ = [
    "ALEPCollector",
    "ALEPECollector",
    "ALESPCollector",
    "ALMGCollector",
    "CamaraDeputadosCollector",
    "GenericHTMLCollector",
    "GenericRSSCollector",
    "IOFMGCollector",
    "LexMLCollector",
    "LexMLPortalCollector",
    "SAPLCollector",
    "SefazSPCollector",
    "SenadoCollector",
]
