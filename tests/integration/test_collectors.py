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
from monitoritcd.collectors.custom._common import parse_iso_date
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

    @pytest.mark.asyncio
    async def test_tjsp_yaml_real_layout(self) -> None:
        # Regression: estrutura real do TJSP /Noticias (validada 2026-05-08)
        # usa <div class="col-sm-9"><a class="noticia-description">
        # <time>...</time><h1>...</h1></a></div>. Garante que selectors
        # do YAML (sources/SP/tjsp.yaml) seguem o layout publicado.
        from pathlib import Path  # noqa: PLC0415

        from monitoritcd.core.source_loader import load_source  # noqa: PLC0415

        repo_root = Path(__file__).resolve().parent.parent.parent  # noqa: ASYNC240
        src = load_source(repo_root / "sources" / "SP" / "tjsp.yaml")

        tjsp_html = """<!DOCTYPE html>
<html><body>
  <div class="col-sm-9">
    <a class="noticia-description" href="/Noticias/Noticia?codigoNoticia=114197&pagina=1">
      <time>08/05/2026</time>
      <h1>Decisão TJSP sobre ITCMD em sucessão</h1>
      <p class="text-justify">Caso envolvendo doação.</p>
    </a>
  </div>
  <div class="col-sm-9">
    <a class="noticia-description" href="https://www.tjsp.jus.br/Noticias/Noticia?codigoNoticia=114191&pagina=1">
      <time>07/05/2026</time>
      <h1>Inventário extrajudicial — novo entendimento</h1>
    </a>
  </div>
</body></html>
"""
        async with respx.mock:
            respx.get("https://www.tjsp.jus.br/Noticias").mock(
                return_value=httpx.Response(200, text=tjsp_html),
            )
            async with GenericHTMLCollector(src) as c:
                items = await c.collect()
        assert len(items) == 2
        assert "ITCMD" in items[0].titulo_raw
        # URL relativa resolvida contra source.url
        assert items[0].url.startswith("https://www.tjsp.jus.br/Noticias/Noticia?")
        # URL absoluta preservada
        assert items[1].url == (
            "https://www.tjsp.jus.br/Noticias/Noticia?codigoNoticia=114191&pagina=1"
        )


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

    def test_iso_date_helper_paths(self) -> None:
        assert parse_iso_date(None) is None
        assert parse_iso_date("") is None
        assert parse_iso_date("nao-eh-iso") is None  # ValueError
        # naive -> default UTC
        d = parse_iso_date("2026-04-25T10:00:00")
        assert d is not None and d.tzinfo is not None
        # com tz preserva
        d2 = parse_iso_date("2026-04-25T10:00:00+02:00")
        assert d2 is not None and d2.utcoffset() is not None
        assert d2.utcoffset().total_seconds() == 2 * 3600  # type: ignore[union-attr]


# ─────────────────────────────────────────────────────────────────────────────
# SefazSP — API SharePoint REST (legislacao.fazenda.sp.gov.br/_api/...)
# ─────────────────────────────────────────────────────────────────────────────

SEFAZ_SP_GUID = "f286d0d1-5624-47da-a856-a8571296eb7f"
SEFAZ_SP_URL_BASE = (
    f"https://legislacao.fazenda.sp.gov.br/_api/Web/Lists(guid'{SEFAZ_SP_GUID}')/Items"
)


def _sefaz_sp_source(**overrides: object) -> Source:
    from monitoritcd.core.models import Source as _Src  # noqa: PLC0415

    selectors = {
        "list_guid": SEFAZ_SP_GUID,
        "palavras_chave": "ITCMD|ITCD|causa mortis",
        "dias": str(365 * 10),  # janela ampla para teste
        "top": "100",
    }
    selectors.update(overrides.get("selectors", {}) or {})  # type: ignore[arg-type]
    return _Src(
        id="sefaz-sp",
        uf="SP",
        nome="SEFAZ-SP",
        tipo=TipoFonte.SEFAZ,
        parser=Parser.SEFAZ_SP,
        url="https://legislacao.fazenda.sp.gov.br/_api/Web/Lists",
        selectors=selectors,
    )


# Payload OData v3 verbose (formato `{"d":{"results":[...]}}`) com 2 atos ITCMD
# e 1 não-ITCMD para validar filtro cliente-side.
SEFAZ_SP_RESPONSE = """{
  "d": {
    "results": [
      {
        "ID": 1525700,
        "Modified": "2026-05-08T15:00:31Z",
        "DataAto": "2026-05-04T03:00:00Z",
        "DataPublicacao": "2026-05-05T03:00:00Z",
        "PesqLegisTitle": "RC 33561/2026",
        "Ementa": "<div><p>ITCMD - Doacao de imovel urbano - Base de calculo.</p></div>",
        "File": {
          "ServerRelativeUrl": "/Paginas/RC33561_2026.aspx",
          "Name": "RC33561_2026.aspx"
        }
      },
      {
        "ID": 1525701,
        "Modified": "2026-05-08T15:00:30Z",
        "DataAto": "2026-05-06T03:00:00Z",
        "DataPublicacao": "2026-05-07T03:00:00Z",
        "PesqLegisTitle": "RC 33582/2026",
        "Ementa": "<div><p>ICMS - Energia eletrica - Sistema de compensacao.</p></div>",
        "File": {
          "ServerRelativeUrl": "/Paginas/RC33582_2026.aspx",
          "Name": "RC33582_2026.aspx"
        }
      },
      {
        "ID": 1525702,
        "Modified": "2026-05-08T15:00:40Z",
        "DataAto": "2026-05-04T03:00:00Z",
        "DataPublicacao": "2026-05-05T03:00:00Z",
        "PesqLegisTitle": "Comunicado DICAR 30 de 2026",
        "Ementa": "Tabela Pratica para Calculo dos Juros de Mora ITCMD e IPVA.",
        "File": {
          "ServerRelativeUrl": "/Paginas/Comunicado-DICAR-30-de-2026.aspx",
          "Name": "Comunicado-DICAR-30-de-2026.aspx"
        }
      }
    ]
  }
}"""


@pytest.mark.integration
class TestSefazSPCollector:
    @pytest.mark.asyncio
    async def test_filters_by_keyword_clientside(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        src = _sefaz_sp_source()
        async with respx.mock:
            respx.get(url__startswith=SEFAZ_SP_URL_BASE).mock(
                return_value=httpx.Response(200, text=SEFAZ_SP_RESPONSE),
            )
            async with SefazSPCollector(src) as c:
                items = await c.collect()
        # ICMS é descartado; RC ITCMD + Comunicado DICAR (com ITCMD) ficam
        assert len(items) == 2
        titulos = sorted(it.titulo_raw for it in items)
        assert titulos == ["Comunicado DICAR 30 de 2026", "RC 33561/2026"]
        # URL é construída a partir de File.ServerRelativeUrl
        for it in items:
            assert it.url.startswith("https://legislacao.fazenda.sp.gov.br/Paginas/")
        # Texto da ementa preserva conteúdo (sem tags HTML)
        rc = next(it for it in items if it.titulo_raw == "RC 33561/2026")
        assert rc.texto_raw is not None
        assert "ITCMD" in rc.texto_raw
        assert "<div>" not in rc.texto_raw  # tags removidas

    @pytest.mark.asyncio
    async def test_missing_list_guid_raises(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        src = _sefaz_sp_source().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "dias": "60"}},
        )
        async with SefazSPCollector(src) as c:
            with pytest.raises(CollectorError, match="list_guid"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_top_raises(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        src = _sefaz_sp_source().model_copy(
            update={
                "selectors": {
                    "list_guid": SEFAZ_SP_GUID,
                    "palavras_chave": "ITCMD",
                    "top": "9999",  # > MAX_TOP (500)
                },
            },
        )
        async with SefazSPCollector(src) as c:
            with pytest.raises(CollectorError, match="top fora do intervalo"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_empty(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        src = _sefaz_sp_source()
        async with respx.mock:
            respx.get(url__startswith=SEFAZ_SP_URL_BASE).mock(
                return_value=httpx.Response(500, text="error"),
            )
            async with SefazSPCollector(src) as c:
                items = await c.collect()
        # Falha de fetch não derruba pipeline — retorna lista vazia
        assert items == []

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        src = _sefaz_sp_source()
        async with respx.mock:
            respx.get(url__startswith=SEFAZ_SP_URL_BASE).mock(
                return_value=httpx.Response(200, text="not json at all"),
            )
            async with SefazSPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_skips_item_without_file_url(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        # Item sem File.ServerRelativeUrl deve ser descartado (sem URL canônica)
        payload = """{
  "d": {
    "results": [
      {
        "ID": 1,
        "Modified": "2026-05-08T15:00:00Z",
        "DataAto": "2026-05-04T03:00:00Z",
        "DataPublicacao": "2026-05-05T03:00:00Z",
        "PesqLegisTitle": "RC ITCMD sem URL",
        "Ementa": "ITCMD",
        "File": {}
      }
    ]
  }
}"""
        src = _sefaz_sp_source()
        async with respx.mock:
            respx.get(url__startswith=SEFAZ_SP_URL_BASE).mock(
                return_value=httpx.Response(200, text=payload),
            )
            async with SefazSPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_skips_item_without_titulo(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        # Sem PesqLegisTitle nem Title → descarta
        payload = """{
  "d": {
    "results": [
      {
        "ID": 1,
        "Modified": "2026-05-08T15:00:00Z",
        "DataAto": "2026-05-04T03:00:00Z",
        "DataPublicacao": "2026-05-05T03:00:00Z",
        "PesqLegisTitle": null,
        "Ementa": "ITCMD",
        "File": {"ServerRelativeUrl": "/Paginas/x.aspx"}
      }
    ]
  }
}"""
        src = _sefaz_sp_source()
        async with respx.mock:
            respx.get(url__startswith=SEFAZ_SP_URL_BASE).mock(
                return_value=httpx.Response(200, text=payload),
            )
            async with SefazSPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_skips_item_outside_window_with_old_modified(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        # Ambos DataPublicacao e Modified antes do cutoff → descarta
        # cutoff default = 60 dias atrás (do _sefaz_sp_source helper, dias=3650)
        # então usa fonte com dias=1 para forçar exclusão de 2024-01-01
        src = _sefaz_sp_source().model_copy(
            update={
                "selectors": {
                    "list_guid": SEFAZ_SP_GUID,
                    "palavras_chave": "ITCMD",
                    "dias": "1",
                    "top": "100",
                },
            },
        )
        payload = """{
  "d": {
    "results": [
      {
        "ID": 1,
        "Modified": "2024-01-01T15:00:00Z",
        "DataAto": "2024-01-01T03:00:00Z",
        "DataPublicacao": "2024-01-01T03:00:00Z",
        "PesqLegisTitle": "RC ITCMD antigo",
        "Ementa": "ITCMD antigo",
        "File": {"ServerRelativeUrl": "/Paginas/old.aspx"}
      }
    ]
  }
}"""
        async with respx.mock:
            respx.get(url__startswith=SEFAZ_SP_URL_BASE).mock(
                return_value=httpx.Response(200, text=payload),
            )
            async with SefazSPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_unexpected_payload_results_not_list(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        # `results` não é lista → log warning + retorno vazio
        payload = '{"d": {"results": "not a list"}}'
        src = _sefaz_sp_source()
        async with respx.mock:
            respx.get(url__startswith=SEFAZ_SP_URL_BASE).mock(
                return_value=httpx.Response(200, text=payload),
            )
            async with SefazSPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_negative_top_raises(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        # top negativo cai no limite inferior (top<=0 raises)
        # Patch direto: com top="0" cfg.page_size é 0 → fallback DEFAULT_TOP=100;
        # mas top negativo dispara o check.
        src = _sefaz_sp_source().model_copy(
            update={
                "selectors": {
                    "list_guid": SEFAZ_SP_GUID,
                    "palavras_chave": "ITCMD",
                    "top": "-5",
                },
            },
        )
        async with SefazSPCollector(src) as c:
            with pytest.raises(CollectorError, match="top fora do intervalo"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_item_without_ementa_uses_titulo_only(self) -> None:
        from monitoritcd.collectors.custom.sefaz_sp import SefazSPCollector  # noqa: PLC0415

        # Item sem Ementa mas com titulo contendo keyword → mantém
        payload = """{
  "d": {
    "results": [
      {
        "ID": 1,
        "Modified": "2026-05-08T15:00:00Z",
        "DataAto": null,
        "DataPublicacao": null,
        "PesqLegisTitle": "Decisao Normativa ITCMD 1/2026",
        "Ementa": null,
        "File": {"ServerRelativeUrl": "/Paginas/DN-1-2026.aspx"}
      }
    ]
  }
}"""
        src = _sefaz_sp_source()
        async with respx.mock:
            respx.get(url__startswith=SEFAZ_SP_URL_BASE).mock(
                return_value=httpx.Response(200, text=payload),
            )
            async with SefazSPCollector(src) as c:
                items = await c.collect()
        assert len(items) == 1
        assert items[0].texto_raw is None  # ementa nula → texto_raw None
        assert items[0].data_publicacao is None  # sem DataAto/Pub → mantém


# ─────────────────────────────────────────────────────────────────────────────
# ALESP — proposituras.zip (dados abertos via streaming-parse)
# ─────────────────────────────────────────────────────────────────────────────

ALESP_URL = "https://www.al.sp.gov.br/repositorioDados/processo_legislativo/proposituras.zip"


def _alesp_source(**overrides: object) -> Source:
    from monitoritcd.core.models import Source as _Src  # noqa: PLC0415

    selectors = {
        "palavras_chave": "ITCMD|ITCD|causa mortis|doação|sucessão",
        "dias": str(365 * 30),  # janela ampla para teste capturar 2018+
        "max_items": "100",
        "naturezas": "1,2,3",
    }
    selectors.update(overrides.get("selectors", {}) or {})  # type: ignore[arg-type]
    return _Src(
        id="alesp-pls",
        uf="SP",
        nome="ALESP",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.ALESP,
        url=ALESP_URL,
        selectors=selectors,
    )


def _build_alesp_zip() -> bytes:
    """Constrói um proposituras.zip mínimo com 4 itens cobrindo cada filtro."""
    import io as _io  # noqa: PLC0415
    import zipfile as _zip  # noqa: PLC0415

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<proposituras>
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <Ementa>Altera Lei 10705/2000 sobre ITCMD para majorar aliquotas progressivamente.</Ementa>
    <DtEntradaSistema>2026-04-15T00:00:00-03:00</DtEntradaSistema>
    <DtPublicacao>2026-04-15T00:00:00-03:00</DtPublicacao>
    <IdDocumento>1000999001</IdDocumento>
    <IdNatureza>1</IdNatureza>
    <NroLegislativo>183</NroLegislativo>
  </propositura>
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <Ementa>Indica ao governador a doacao de equipamentos para o municipio.</Ementa>
    <DtEntradaSistema>2026-04-20T00:00:00-03:00</DtEntradaSistema>
    <DtPublicacao>2026-04-20T00:00:00-03:00</DtPublicacao>
    <IdDocumento>1000999002</IdDocumento>
    <IdNatureza>9</IdNatureza>
    <NroLegislativo>3437</NroLegislativo>
  </propositura>
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <Ementa>Lei sobre transito - tema irrelevante.</Ementa>
    <DtEntradaSistema>2026-04-22T00:00:00-03:00</DtEntradaSistema>
    <DtPublicacao>2026-04-22T00:00:00-03:00</DtPublicacao>
    <IdDocumento>1000999003</IdDocumento>
    <IdNatureza>1</IdNatureza>
    <NroLegislativo>200</NroLegislativo>
  </propositura>
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <Ementa>PEC sucessão patrimonial e regime de bens.</Ementa>
    <DtEntradaSistema>2026-04-25T00:00:00-03:00</DtEntradaSistema>
    <DtPublicacao>2026-04-25T00:00:00-03:00</DtPublicacao>
    <IdDocumento>1000999004</IdDocumento>
    <IdNatureza>2</IdNatureza>
    <NroLegislativo>15</NroLegislativo>
  </propositura>
</proposituras>
"""
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
        zf.writestr("proposituras.xml", xml)
    return buf.getvalue()


@pytest.mark.integration
class TestALESPCollector:
    @pytest.mark.asyncio
    async def test_collects_recent_with_keyword_and_natureza(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        src = _alesp_source()
        zip_bytes = _build_alesp_zip()
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(
                    200,
                    content=zip_bytes,
                    headers={"content-type": "application/zip"},
                ),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        # Esperado: 2 items
        # - PL 183/2026 ITCMD (natureza=1, keyword OK)  ✅
        # - PEC 15/2026 sucessão (natureza=2, keyword OK) ✅
        # - Indicação 3437 doacao (natureza=9 não permitida) ❌
        # - PL 200/2026 transito (sem keyword) ❌
        assert len(items) == 2
        nro_set = {it.titulo_raw for it in items}
        assert "Projeto de Lei 183/2026" in nro_set
        assert "Proposta de Emenda Constitucional 15/2026" in nro_set
        # URL pública construída a partir de IdDocumento
        for it in items:
            assert it.url.startswith("https://www.al.sp.gov.br/propositura/?id=10009990")

    @pytest.mark.asyncio
    async def test_max_items_caps(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        src = _alesp_source(selectors={"max_items": "1", "naturezas": "1,2"})
        zip_bytes = _build_alesp_zip()
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(200, content=zip_bytes),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_invalid_dias_raises(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        src = _alesp_source(selectors={"dias": "abc"})
        async with ALESPCollector(src) as c:
            with pytest.raises(CollectorError, match="dias inválido"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_empty_keywords_raises(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        src = _alesp_source(selectors={"palavras_chave": "  |  "})
        async with ALESPCollector(src) as c:
            with pytest.raises(CollectorError, match="palavras_chave"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_oversized_zip_aborts(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415
        from monitoritcd.core import limits as _lim  # noqa: PLC0415

        # Constrói payload acima do hard cap — fingimos um ZIP de 51 MB
        big = b"x" * (_lim.MAX_OPEN_DATA_BYTES + 1024)
        src = _alesp_source()
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(200, content=big),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        # Falha de fetch é tratada como warning + lista vazia
        assert items == []

    @pytest.mark.asyncio
    async def test_invalid_zip_returns_empty(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        src = _alesp_source()
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(200, content=b"not a zip"),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_zip_without_proposituras_xml_returns_empty(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        # ZIP válido mas sem o arquivo proposituras.xml dentro
        import io as _io  # noqa: PLC0415
        import zipfile as _zip  # noqa: PLC0415

        buf = _io.BytesIO()
        with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
            zf.writestr("outroarquivo.xml", "<root/>")
        zip_bytes = buf.getvalue()

        src = _alesp_source()
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(200, content=zip_bytes),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        # ZIP válido mas sem proposituras.xml → CollectorError convertido em []
        # (warning logged em alesp.parse_failed)
        assert items == []

    @pytest.mark.asyncio
    async def test_skips_propositura_without_ementa(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        import io as _io  # noqa: PLC0415
        import zipfile as _zip  # noqa: PLC0415

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<proposituras>
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <Ementa></Ementa>
    <DtEntradaSistema>2026-04-15T00:00:00-03:00</DtEntradaSistema>
    <IdDocumento>1</IdDocumento>
    <IdNatureza>1</IdNatureza>
    <NroLegislativo>1</NroLegislativo>
  </propositura>
</proposituras>
"""
        buf = _io.BytesIO()
        with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
            zf.writestr("proposituras.xml", xml)

        src = _alesp_source()
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(200, content=buf.getvalue()),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_skips_propositura_with_invalid_date(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        import io as _io  # noqa: PLC0415
        import zipfile as _zip  # noqa: PLC0415

        # Data inválida → cai no `dt = None` → mantém (não filtra por data)
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<proposituras>
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <Ementa>ITCMD propositura sem data válida.</Ementa>
    <DtEntradaSistema>data-invalida</DtEntradaSistema>
    <IdDocumento>1</IdDocumento>
    <IdNatureza>1</IdNatureza>
    <NroLegislativo>1</NroLegislativo>
  </propositura>
</proposituras>
"""
        buf = _io.BytesIO()
        with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
            zf.writestr("proposituras.xml", xml)

        src = _alesp_source()
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(200, content=buf.getvalue()),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        # Data inválida → dt=None → não filtra; mantém
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_skips_propositura_missing_id_or_numero(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        import io as _io  # noqa: PLC0415
        import zipfile as _zip  # noqa: PLC0415

        # Sem IdDocumento → descarta
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<proposituras>
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <Ementa>ITCMD sem ID.</Ementa>
    <DtEntradaSistema>2026-04-15T00:00:00-03:00</DtEntradaSistema>
    <IdNatureza>1</IdNatureza>
    <NroLegislativo>1</NroLegislativo>
  </propositura>
</proposituras>
"""
        buf = _io.BytesIO()
        with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
            zf.writestr("proposituras.xml", xml)

        src = _alesp_source()
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(200, content=buf.getvalue()),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_natureza_unknown_uses_fallback_titulo(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        import io as _io  # noqa: PLC0415
        import zipfile as _zip  # noqa: PLC0415

        # Natureza fora de NATUREZA_NOMES → fallback "Tipo X N/Y"
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<proposituras>
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <Ementa>ITCMD com natureza desconhecida.</Ementa>
    <DtEntradaSistema>2026-04-15T00:00:00-03:00</DtEntradaSistema>
    <IdDocumento>9999</IdDocumento>
    <IdNatureza>99</IdNatureza>
    <NroLegislativo>50</NroLegislativo>
  </propositura>
</proposituras>
"""
        buf = _io.BytesIO()
        with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
            zf.writestr("proposituras.xml", xml)

        # Sem filtro de naturezas → aceita qualquer
        src = _alesp_source(selectors={"naturezas": ""})
        async with respx.mock:
            respx.get(url__startswith="https://www.al.sp.gov.br/repositorioDados/").mock(
                return_value=httpx.Response(200, content=buf.getvalue()),
            )
            async with ALESPCollector(src) as c:
                items = await c.collect()
        assert len(items) == 1
        assert items[0].titulo_raw == "Tipo 99 50/2026"

    @pytest.mark.asyncio
    async def test_invalid_max_items_raises(self) -> None:
        from monitoritcd.collectors.custom.alesp import ALESPCollector  # noqa: PLC0415

        src = _alesp_source(selectors={"max_items": "abc"})
        async with ALESPCollector(src) as c:
            with pytest.raises(CollectorError, match="max_items inválido"):
                await c.collect()
