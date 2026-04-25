"""Testes de integração dos collectors.

Usa `respx` para mockar httpx (sem rede real). Cassettes VCR podem ser
adicionados em fase posterior para validação contra fontes reais.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from monitoritcd.collectors import (
    ALMGCollector,
    GenericHTMLCollector,
    GenericRSSCollector,
    LexMLCollector,
)
from monitoritcd.core.base_collector import CollectorError, _DomainRateLimiter
from monitoritcd.core.models import Parser, Source, TipoFonte

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    _DomainRateLimiter._reset_for_tests()


def _rss_source(url: str = "https://www.example.gov.br/feed.xml") -> Source:
    return Source(
        id="rss-test",
        uf="_federal",
        nome="RSS Test",
        tipo=TipoFonte.NOTICIA,
        parser=Parser.GENERIC_RSS,
        url=url,
    )


def _html_source(url: str = "https://www.example.gov.br/atos") -> Source:
    return Source(
        id="html-test",
        uf="SP",
        nome="HTML Test",
        tipo=TipoFonte.SEFAZ,
        parser=Parser.GENERIC_HTML,
        url=url,
        selectors={
            "item": "article.ato",
            "titulo": "h2.titulo",
            "link": "a@href",
        },
    )


def _lexml_source() -> Source:
    return Source(
        id="lexml-test",
        uf="_federal",
        nome="LexML Test",
        tipo=TipoFonte.JURISPRUDENCIA,
        parser=Parser.LEXML,
        url="https://www.lexml.gov.br/busca/SRU",
        selectors={"query": "ITCMD", "max_records": "5"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Generic RSS
# ─────────────────────────────────────────────────────────────────────────────

VALID_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Conjur — Tributário</title>
    <link>https://www.example.gov.br/</link>
    <description>Tributário</description>
    <item>
      <title>STF decide modulação de ITCMD em RJ</title>
      <link>https://www.example.gov.br/post/123</link>
      <guid>https://www.example.gov.br/post/123</guid>
      <pubDate>Mon, 22 Apr 2026 10:00:00 -0300</pubDate>
      <description>Decisão do STF afeta jurisprudência sobre ITCMD.</description>
    </item>
    <item>
      <title>SEFAZ-SP publica IN sobre ITCMD progressivo</title>
      <link>https://www.example.gov.br/post/124</link>
      <pubDate>Tue, 23 Apr 2026 10:00:00 -0300</pubDate>
      <description>Nova IN da SEFAZ-SP.</description>
    </item>
  </channel>
</rss>
"""


@pytest.mark.integration
class TestGenericRSS:
    @pytest.mark.asyncio
    async def test_collects_two_items(self) -> None:
        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=httpx.Response(200, text=VALID_RSS),
            )
            async with GenericRSSCollector(_rss_source()) as c:
                items = await c.collect()
        assert len(items) == 2
        assert items[0].titulo_raw.startswith("STF decide")
        assert items[0].url == "https://www.example.gov.br/post/123"
        assert items[0].data_publicacao is not None

    @pytest.mark.asyncio
    async def test_skips_entry_without_title(self) -> None:
        rss = VALID_RSS.replace(
            "<title>STF decide modulação de ITCMD em RJ</title>", "<title></title>"
        )
        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=httpx.Response(200, text=rss),
            )
            async with GenericRSSCollector(_rss_source()) as c:
                items = await c.collect()
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_empty_feed_with_bozo_raises(self) -> None:
        # XML totalmente quebrado, sem entries → CollectorError
        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=httpx.Response(200, text="<<<not xml at all"),
            )
            async with GenericRSSCollector(_rss_source()) as c:
                with pytest.raises(CollectorError):
                    await c.collect()

    @pytest.mark.asyncio
    async def test_atom_with_content_array(self) -> None:
        # Atom feed com <content> (array) ao invés de <description>
        atom = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test feed</title>
  <entry>
    <title>Título Atom</title>
    <link href="https://www.example.gov.br/post/1"/>
    <id>https://www.example.gov.br/post/1</id>
    <content type="html">Conteúdo do post sobre ITCMD.</content>
  </entry>
</feed>
"""
        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=httpx.Response(200, text=atom),
            )
            async with GenericRSSCollector(_rss_source()) as c:
                items = await c.collect()
        assert len(items) == 1
        assert items[0].titulo_raw == "Título Atom"
        assert items[0].texto_raw is not None
        assert "ITCMD" in items[0].texto_raw

    @pytest.mark.asyncio
    async def test_entry_without_pubdate(self) -> None:
        rss = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>x</title>
  <item>
    <title>Sem data</title>
    <link>https://www.example.gov.br/sd</link>
  </item>
</channel></rss>"""
        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=httpx.Response(200, text=rss),
            )
            async with GenericRSSCollector(_rss_source()) as c:
                items = await c.collect()
        assert len(items) == 1
        assert items[0].data_publicacao is None


# ─────────────────────────────────────────────────────────────────────────────
# Generic HTML
# ─────────────────────────────────────────────────────────────────────────────

VALID_HTML = """<!DOCTYPE html>
<html><body>
  <article class="ato">
    <h2 class="titulo">Decreto 12345/2026 — ITCMD</h2>
    <a href="/atos/decreto-12345">Ler mais</a>
  </article>
  <article class="ato">
    <h2 class="titulo">Portaria 78 — Tabela ITCMD 2026</h2>
    <a href="https://www.example.gov.br/atos/portaria-78">Ler mais</a>
  </article>
</body></html>
"""


@pytest.mark.integration
class TestGenericHTML:
    @pytest.mark.asyncio
    async def test_collects_html_items(self) -> None:
        async with respx.mock:
            respx.get("https://www.example.gov.br/atos").mock(
                return_value=httpx.Response(200, text=VALID_HTML),
            )
            async with GenericHTMLCollector(_html_source()) as c:
                items = await c.collect()
        assert len(items) == 2
        assert "Decreto 12345" in items[0].titulo_raw
        # URL relativa foi resolvida contra source.url
        assert items[0].url == "https://www.example.gov.br/atos/decreto-12345"
        # URL absoluta preservada
        assert items[1].url == "https://www.example.gov.br/atos/portaria-78"

    @pytest.mark.asyncio
    async def test_missing_selectors_raises(self) -> None:
        src = Source(
            id="bad",
            uf="SP",
            nome="x",
            tipo=TipoFonte.SEFAZ,
            parser=Parser.GENERIC_HTML,
            url="https://www.example.gov.br/",
        )
        async with GenericHTMLCollector(src) as c:
            with pytest.raises(CollectorError, match="selectors"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_missing_required_selector_raises(self) -> None:
        # selectors presentes mas sem `link` (obrigatório)
        src = Source(
            id="bad-sel",
            uf="SP",
            nome="x",
            tipo=TipoFonte.SEFAZ,
            parser=Parser.GENERIC_HTML,
            url="https://www.example.gov.br/",
            selectors={"item": "div", "titulo": "h2"},  # falta `link`
        )
        async with GenericHTMLCollector(src) as c:
            with pytest.raises(CollectorError, match="obrigatórios"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_skips_item_without_titulo(self) -> None:
        html = '<article class="ato"><a href="/x"></a></article>'  # sem titulo
        async with respx.mock:
            respx.get("https://www.example.gov.br/atos").mock(
                return_value=httpx.Response(200, text=html),
            )
            async with GenericHTMLCollector(_html_source()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_extract_text_only_when_no_at_in_selector(self) -> None:
        # Selector "h2.titulo" sem @ → extrai texto
        html = (
            '<article class="ato">'
            '<h2 class="titulo">Título A</h2>'
            "<a>texto link</a>"  # sem href
            "</article>"
        )
        src = _html_source().model_copy(
            update={
                "selectors": {
                    "item": "article.ato",
                    "titulo": "h2.titulo",
                    "link": "a",  # sem @ → tenta texto
                },
            },
        )
        async with respx.mock:
            respx.get("https://www.example.gov.br/atos").mock(
                return_value=httpx.Response(200, text=html),
            )
            async with GenericHTMLCollector(src) as c:
                items = await c.collect()
        assert len(items) == 1
        # link foi extraído como texto (e resolvido contra base)
        assert items[0].url.endswith("texto link") or "texto" in items[0].url


# ─────────────────────────────────────────────────────────────────────────────
# LexML
# ─────────────────────────────────────────────────────────────────────────────

LEXML_SRU_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
  <srw:numberOfRecords>2</srw:numberOfRecords>
  <srw:records>
    <srw:record>
      <srw:recordSchema>info:srw/schema/1/dc-v1.1</srw:recordSchema>
      <srw:recordData>
        <srw_dc:dc xmlns:srw_dc="info:srw/schema/1/dc-schema"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Lei nº 14.789, de 2026 — ITCMD federal</dc:title>
          <dc:identifier>https://www.lexml.gov.br/urn/urn:lex:br:federal:lei:2026-04-15;14789</dc:identifier>
          <dc:date>2026-04-15</dc:date>
          <dc:type>Lei Ordinária</dc:type>
        </srw_dc:dc>
      </srw:recordData>
    </srw:record>
    <srw:record>
      <srw:recordData>
        <srw_dc:dc xmlns:srw_dc="info:srw/schema/1/dc-schema"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Decreto 11.234/2026 — Regulamenta ITCMD</dc:title>
          <dc:identifier>https://www.lexml.gov.br/urn/urn:lex:br:federal:decreto:2026-04-20;11234</dc:identifier>
          <dc:date>2026-04-20</dc:date>
          <dc:type>Decreto</dc:type>
        </srw_dc:dc>
      </srw:recordData>
    </srw:record>
  </srw:records>
</srw:searchRetrieveResponse>
"""


@pytest.mark.integration
class TestLexML:
    @pytest.mark.asyncio
    async def test_parses_sru_records(self) -> None:
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/SRU").mock(
                return_value=httpx.Response(200, text=LEXML_SRU_RESPONSE),
            )
            async with LexMLCollector(_lexml_source()) as c:
                items = await c.collect()
        assert len(items) == 2
        assert "14.789" in items[0].titulo_raw
        assert items[0].url.startswith("https://www.lexml.gov.br/urn/")
        assert items[0].data_publicacao is not None
        assert items[0].data_publicacao.year == 2026

    @pytest.mark.asyncio
    async def test_skips_records_without_title(self) -> None:
        no_title = LEXML_SRU_RESPONSE.replace(
            "<dc:title>Lei nº 14.789, de 2026 — ITCMD federal</dc:title>",
            "<dc:title></dc:title>",
        )
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/SRU").mock(
                return_value=httpx.Response(200, text=no_title),
            )
            async with LexMLCollector(_lexml_source()) as c:
                items = await c.collect()
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_empty_response(self) -> None:
        empty = """<?xml version="1.0"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
  <srw:numberOfRecords>0</srw:numberOfRecords>
  <srw:records></srw:records>
</srw:searchRetrieveResponse>
"""
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/SRU").mock(
                return_value=httpx.Response(200, text=empty),
            )
            async with LexMLCollector(_lexml_source()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_invalid_max_records_raises(self) -> None:
        src = _lexml_source()
        src_with_bad = src.model_copy(
            update={"selectors": {"query": "ITCMD", "max_records": "not-a-number"}},
        )
        async with LexMLCollector(src_with_bad) as c:
            with pytest.raises(CollectorError, match="max_records"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_date_in_record_does_not_crash(self) -> None:
        bad_date = LEXML_SRU_RESPONSE.replace("2026-04-15", "data-invalida")
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/SRU").mock(
                return_value=httpx.Response(200, text=bad_date),
            )
            async with LexMLCollector(_lexml_source()) as c:
                items = await c.collect()
        # Item ainda é coletado, só sem data
        assert len(items) == 2
        assert items[0].data_publicacao is None

    @pytest.mark.asyncio
    async def test_default_selectors_when_none(self) -> None:
        # Source sem selectors → usa defaults do collector
        src = _lexml_source().model_copy(update={"selectors": None})
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/SRU").mock(
                return_value=httpx.Response(200, text=LEXML_SRU_RESPONSE),
            )
            async with LexMLCollector(src) as c:
                items = await c.collect()
        assert len(items) == 2


# ─────────────────────────────────────────────────────────────────────────────
# ALMG (Assembleia Legislativa de Minas Gerais)
# ─────────────────────────────────────────────────────────────────────────────


def _almg_source(modo: str = "legislacao") -> Source:
    base = "https://dadosabertos.almg.gov.br/api/v2"
    if modo == "proposicoes":
        url = f"{base}/proposicoes/pesquisa/direcionada"
    else:
        url = f"{base}/legislacao/mineira/pesquisa/direcionada"
    return Source(
        id=f"almg-{modo}",
        uf="MG",
        nome=f"ALMG {modo}",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.ALMG,
        url=url,
        selectors={
            "modo": modo,
            "palavras_chave": "ITCMD",
            "dias": str(365 * 10),  # tudo, para o teste
        },
    )


ALMG_LEGIS_RESPONSE = """{
  "resultado": {
    "noOcorrencias": 1,
    "listaItem": [
      {
        "numDoc": "000121965",
        "norma": "Lei 25825 2026",
        "tipo": "LEI",
        "numero": "25825",
        "ano": "2026",
        "data": "20260422",
        "origem": "Legislativo",
        "ementa": "Disciplina ITCMD em casos de heranca digital."
      }
    ]
  }
}"""


ALMG_PROP_RESPONSE = """{
  "resultado": {
    "noOcorrencias": 1,
    "listaItem": [
      {
        "tipoProjeto": "PROJETO DE LEI",
        "siglaTipoProjeto": "PL",
        "numero": "1234",
        "ano": "2026",
        "autor": "Dep. Fulano",
        "assunto": "Aumenta aliquota do ITCMD para grandes fortunas.",
        "situacao": "Em tramitacao",
        "dataPublicacao": "2026-04-20",
        "numeroDoc": "000999888",
        "proposicao": "PL 1234 2026 - PROJETO DE LEI"
      }
    ]
  }
}"""


@pytest.mark.integration
class TestALMGCollector:
    @pytest.mark.asyncio
    async def test_legislacao_parses_response(self) -> None:
        src = _almg_source(modo="legislacao")
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.almg.gov.br/").mock(
                return_value=httpx.Response(200, text=ALMG_LEGIS_RESPONSE),
            )
            async with ALMGCollector(src) as c:
                items = await c.collect()
        assert len(items) == 1
        assert items[0].titulo_raw == "Lei 25825 2026"
        assert "heranca digital" in (items[0].texto_raw or "")
        assert items[0].url.startswith("https://www.almg.gov.br/legislacao-mineira/lei/25825/2026")
        assert items[0].data_publicacao is not None
        assert items[0].data_publicacao.year == 2026

    @pytest.mark.asyncio
    async def test_proposicoes_parses_response(self) -> None:
        src = _almg_source(modo="proposicoes")
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.almg.gov.br/").mock(
                return_value=httpx.Response(200, text=ALMG_PROP_RESPONSE),
            )
            async with ALMGCollector(src) as c:
                items = await c.collect()
        assert len(items) == 1
        assert "PL 1234" in items[0].titulo_raw
        assert "tramitacao-projetos" in items[0].url
        assert "Dep. Fulano" in (items[0].texto_raw or "")

    @pytest.mark.asyncio
    async def test_dedupe_across_keywords(self) -> None:
        # Mesmo doc retornado para 2 keywords → deve aparecer só 1 vez
        src = _almg_source(modo="legislacao").model_copy(
            update={
                "selectors": {
                    "modo": "legislacao",
                    "palavras_chave": "ITCMD|ITCD",
                    "dias": "3650",
                },
            },
        )
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.almg.gov.br/").mock(
                return_value=httpx.Response(200, text=ALMG_LEGIS_RESPONSE),
            )
            async with ALMGCollector(src) as c:
                items = await c.collect()
        assert len(items) == 1  # numDoc 000121965 deduped

    @pytest.mark.asyncio
    async def test_filter_by_dias(self) -> None:
        # Item de 2026-04-22, com dias=1 e teste rodando muito depois → filtrado
        src = _almg_source(modo="legislacao").model_copy(
            update={
                "selectors": {
                    "modo": "legislacao",
                    "palavras_chave": "ITCMD",
                    "dias": "1",
                },
            },
        )
        old_response = ALMG_LEGIS_RESPONSE.replace("20260422", "20200101")
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.almg.gov.br/").mock(
                return_value=httpx.Response(200, text=old_response),
            )
            async with ALMGCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_invalid_modo_raises(self) -> None:
        src = _almg_source(modo="legislacao").model_copy(
            update={"selectors": {"modo": "invalido", "palavras_chave": "X"}},
        )
        async with ALMGCollector(src) as c:
            with pytest.raises(CollectorError, match="modo ALMG inválido"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_empty_keywords_raises(self) -> None:
        src = _almg_source(modo="legislacao").model_copy(
            update={"selectors": {"modo": "legislacao", "palavras_chave": "  |  "}},
        )
        async with ALMGCollector(src) as c:
            with pytest.raises(CollectorError, match="palavras_chave"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_json_logs_and_continues(self) -> None:
        src = _almg_source(modo="legislacao")
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.almg.gov.br/").mock(
                return_value=httpx.Response(200, text="not json"),
            )
            async with ALMGCollector(src) as c:
                items = await c.collect()
        # JSON invalido nao derruba — só loga e segue
        assert items == []

    @pytest.mark.asyncio
    async def test_invalid_dias_raises(self) -> None:
        src = _almg_source(modo="legislacao").model_copy(
            update={"selectors": {"modo": "legislacao", "palavras_chave": "X", "dias": "abc"}},
        )
        async with ALMGCollector(src) as c:
            with pytest.raises(CollectorError, match="dias inválido"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_fetch_failure_does_not_raise(self) -> None:
        src = _almg_source(modo="legislacao")
        async with respx.mock:
            # Todas as tentativas retornam 500 — tenacity desiste, CollectorError captado
            respx.get(url__startswith="https://dadosabertos.almg.gov.br/").mock(
                return_value=httpx.Response(500),
            )
            async with ALMGCollector(src) as c:
                items = await c.collect()
        assert items == []  # falha não derruba pipeline

    @pytest.mark.asyncio
    async def test_legislacao_skips_item_without_required_fields(self) -> None:
        src = _almg_source(modo="legislacao")
        bad_response = """{"resultado": {"listaItem": [{"numDoc": "X", "tipo": "LEI"}]}}"""
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.almg.gov.br/").mock(
                return_value=httpx.Response(200, text=bad_response),
            )
            async with ALMGCollector(src) as c:
                items = await c.collect()
        # numero e ano ausentes → item descartado silenciosamente
        assert items == []

    @pytest.mark.asyncio
    async def test_proposicao_skips_item_without_required_fields(self) -> None:
        src = _almg_source(modo="proposicoes")
        bad_response = (
            '{"resultado": {"listaItem": [{"numeroDoc": "X", "siglaTipoProjeto": "PL"}]}}'
        )
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.almg.gov.br/").mock(
                return_value=httpx.Response(200, text=bad_response),
            )
            async with ALMGCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_compact_date_invalid_returns_none(self) -> None:
        from monitoritcd.collectors.custom.almg import _parse_compact_date  # noqa: PLC0415

        assert _parse_compact_date(None) is None
        assert _parse_compact_date("") is None
        assert _parse_compact_date("notadate") is None
        assert _parse_compact_date("20260230") is None  # 30 fev: dia inválido
