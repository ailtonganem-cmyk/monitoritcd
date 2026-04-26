"""Testes dos feeds estáticos (RSS/Atom/JSON Feed) e ICS."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from monitoritcd.core.models import (
    Documento,
    LLMResult,
    Parser,
    RawItem,
    SeverityTier,
    Source,
    StatusDocumento,
    TipoAto,
    TipoFonte,
)
from monitoritcd.notifiers.feeds import (
    build_atom_feed,
    build_feeds_per_relevancia,
    build_feeds_per_tipo,
    build_feeds_per_uf,
    build_json_feed,
    build_rss_feed,
)
from monitoritcd.notifiers.ics import build_ics

NOW = datetime(2026, 4, 24, tzinfo=UTC)


def _doc(uf: str = "SP", relev: int = 7, tipo: TipoAto = TipoAto.PROJETO_LEI) -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw=f"PL {relev}/2026 ({uf})",
        url=f"https://x.gov.br/{relev}",
        fetched_at=NOW,
        data_publicacao=NOW,
        content_hash="a" * 64,
    )
    src = Source(
        id="src",
        uf=uf,
        nome="x",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = LLMResult(
        classified_at=NOW,
        llm_model="x",
        llm_prompt_version="v1",
        tipo=tipo,
        relevancia=relev,
        severity_tier=SeverityTier.NORMAL,
        resumo="resumo",
    )
    return Documento(
        owner_id="o",
        doc_id=f"d_{uf}_{relev}_{tipo.value}",
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )


@pytest.mark.unit
class TestRSS:
    def test_basic(self) -> None:
        feed = build_rss_feed([_doc()], title="Test")
        assert "<rss" in feed
        assert "PL 7/2026" in feed
        assert "<channel>" in feed

    def test_empty(self) -> None:
        feed = build_rss_feed([], title="Empty")
        assert "<channel>" in feed

    def test_xml_escape(self) -> None:
        # Título com caracteres XML especiais
        raw = RawItem(
            source_id="x",
            titulo_raw="<script>alert(1)</script>",
            url="https://x.gov.br/",
            fetched_at=NOW,
            content_hash="a" * 64,
        )
        src = Source(
            id="x",
            uf="SP",
            nome="x",
            tipo=TipoFonte.NOTICIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        doc = Documento(owner_id="o", doc_id="d_xss", source=src, original=raw)
        feed = build_rss_feed([doc], title="x")
        assert "<script>" not in feed
        assert "&lt;script&gt;" in feed


@pytest.mark.unit
class TestAtom:
    def test_basic(self) -> None:
        feed = build_atom_feed([_doc()], title="x", feed_id="test:atom")
        assert "<feed" in feed
        assert "<entry>" in feed

    def test_per_uf(self) -> None:
        docs = [_doc(uf="SP"), _doc(uf="RJ")]
        feeds = build_feeds_per_uf(docs)
        assert "SP" in feeds
        assert "RJ" in feeds

    def test_per_tipo(self) -> None:
        docs = [_doc(tipo=TipoAto.PROJETO_LEI), _doc(tipo=TipoAto.DECRETO, relev=5)]
        feeds = build_feeds_per_tipo(docs)
        assert "projeto_lei" in feeds
        assert "decreto" in feeds

    def test_per_relevancia_filtra(self) -> None:
        docs = [_doc(relev=3), _doc(relev=8)]
        feed = build_feeds_per_relevancia(docs, threshold=7)
        # Apenas o de relevância 8 entra
        assert "PL 8/2026" in feed
        assert "PL 3/2026" not in feed


@pytest.mark.unit
class TestJSONFeed:
    def test_valid_json(self) -> None:
        feed = build_json_feed([_doc()], title="x")
        data = json.loads(feed)
        assert data["version"].startswith("https://jsonfeed.org/")
        assert len(data["items"]) == 1

    def test_empty(self) -> None:
        data = json.loads(build_json_feed([], title="x"))
        assert data["items"] == []


@pytest.mark.unit
class TestICS:
    def test_basic(self) -> None:
        ics = build_ics([_doc()])
        assert "BEGIN:VCALENDAR" in ics
        assert "BEGIN:VEVENT" in ics
        assert "END:VEVENT" in ics
        assert "END:VCALENDAR" in ics

    def test_doc_sem_data_pulado(self) -> None:
        raw = RawItem(
            source_id="x",
            titulo_raw="sem data",
            url="https://x.gov.br/",
            fetched_at=NOW,
            content_hash="a" * 64,
            # sem data_publicacao
        )
        src = Source(
            id="x",
            uf="SP",
            nome="x",
            tipo=TipoFonte.NOTICIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        doc = Documento(owner_id="o", doc_id="d_no_date", source=src, original=raw)
        ics = build_ics([doc])
        # Doc sem data não vira VEVENT, mas calendário ainda é válido
        assert "BEGIN:VCALENDAR" in ics
        assert "BEGIN:VEVENT" not in ics

    def test_escape_caracteres_especiais(self) -> None:
        # Título com vírgula e ponto-e-vírgula precisa escape ICS
        raw = RawItem(
            source_id="x",
            titulo_raw="Lei 1,234; revoga 5",
            url="https://x.gov.br/",
            fetched_at=NOW,
            data_publicacao=NOW,
            content_hash="a" * 64,
        )
        src = Source(
            id="x",
            uf="SP",
            nome="x",
            tipo=TipoFonte.NOTICIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        doc = Documento(owner_id="o", doc_id="d_esc", source=src, original=raw)
        ics = build_ics([doc])
        assert "Lei 1\\,234\\; revoga 5" in ics
