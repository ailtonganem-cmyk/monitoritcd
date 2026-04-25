"""Testes do LexMLPortalCollector com fixture HTML real."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from monitoritcd.collectors import LexMLPortalCollector
from monitoritcd.core.base_collector import _DomainRateLimiter
from monitoritcd.core.models import Parser, Source, TipoFonte

FIXTURE = Path(__file__).parent.parent / "fixtures" / "lexml_portal_search.html"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    _DomainRateLimiter._reset_for_tests()


def _src(localidades: str = "") -> Source:
    return Source(
        id="lexml-portal-test",
        uf="_federal",
        nome="LexML Portal Test",
        tipo=TipoFonte.JURISPRUDENCIA,
        parser=Parser.LEXML_PORTAL,
        url="https://www.lexml.gov.br/busca/search",
        selectors={
            "palavras_chave": "ITCMD",
            "tipo_documento": "Legislação",
            "localidades": localidades,
        },
    )


@pytest.mark.integration
class TestLexMLPortalCollector:
    @pytest.mark.asyncio
    async def test_parses_real_html_fixture(self) -> None:
        """Fixture é HTML capturado da busca real (60KB, 56 hits)."""
        html = FIXTURE.read_text(encoding="utf-8")
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/search").mock(
                return_value=httpx.Response(200, text=html),
            )
            async with LexMLPortalCollector(_src()) as c:
                items = await c.collect()
        # Sem filtro de localidade: deve coletar todos os hits válidos
        assert len(items) >= 5
        # Confirma extração da Lei SP 10.705/2000 (a do ITCMD em SP)
        sp_lei = next((it for it in items if "10.705" in it.titulo_raw), None)
        assert sp_lei is not None, "Lei SP 10.705/2000 não encontrada"
        assert sp_lei.url.endswith("urn:lex:br;sao.paulo:estadual:lei:2000-12-28;10705")
        assert sp_lei.data_publicacao is not None
        assert sp_lei.data_publicacao.year == 2000

    @pytest.mark.asyncio
    async def test_filter_localidade_sao_paulo(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/search").mock(
                return_value=httpx.Response(200, text=html),
            )
            async with LexMLPortalCollector(_src(localidades="sao.paulo")) as c:
                items = await c.collect()
        # Só items SP devem passar
        for it in items:
            assert "sao.paulo" in it.url

    @pytest.mark.asyncio
    async def test_empty_keywords_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "  |  ", "tipo_documento": "Legislação"}},
        )
        async with LexMLPortalCollector(src) as c:
            with pytest.raises(CollectorError, match="palavras_chave"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_html_returns_empty(self) -> None:
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/search").mock(
                return_value=httpx.Response(200, text="<html><body>error</body></html>"),
            )
            async with LexMLPortalCollector(_src()) as c:
                items = await c.collect()
        # Sem div.docHit → lista vazia, sem crash
        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_failure_continues_to_next_keyword(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "ITCMD",
                    "tipo_documento": "Legislação",
                },
            },
        )
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/search").mock(
                side_effect=CollectorError("simulated"),
            )
            async with LexMLPortalCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_dedupe_same_urn_across_keywords(self) -> None:
        """URN repetida entre buscas diferentes deve aparecer só 1x."""
        html = FIXTURE.read_text(encoding="utf-8")
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "ITCMD|ITCD|sucessão",
                    "tipo_documento": "Legislação",
                    "localidades": "",
                },
            },
        )
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/search").mock(
                return_value=httpx.Response(200, text=html),
            )
            async with LexMLPortalCollector(src) as c:
                items = await c.collect()
        # 3 keywords retornam mesma fixture → URN dedup garante mesmo count que 1 keyword
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/search").mock(
                return_value=httpx.Response(200, text=html),
            )
            async with LexMLPortalCollector(_src()) as c:
                single = await c.collect()
        assert len(items) == len(single)

    @pytest.mark.asyncio
    async def test_skips_hit_without_urn(self) -> None:
        """Resultado sem campo URN é silenciosamente descartado."""
        html_no_urn = """
            <html><body>
            <div class="docHit"><table>
                <tr><td>1</td><td><b>Localidade</b></td><td>São Paulo</td><td></td></tr>
                <tr><td></td><td><b>Título</b></td><td><a href="/x">Lei sem URN</a></td><td></td></tr>
            </table></div>
            </body></html>
        """
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/search").mock(
                return_value=httpx.Response(200, text=html_no_urn),
            )
            async with LexMLPortalCollector(_src()) as c:
                items = await c.collect()
        assert items == []  # URN ausente → descartado

    @pytest.mark.asyncio
    async def test_invalid_date_does_not_crash(self) -> None:
        """Data malformada (não DD/MM/YYYY) → data_publicacao=None."""
        html_bad_date = """
            <html><body>
            <div class="docHit"><table>
                <tr><td>1</td><td><b>Título</b></td>
                    <td><a href="/urn/x">Lei x</a></td><td></td></tr>
                <tr><td></td><td><b>Data</b></td><td>data-invalida</td><td></td></tr>
                <tr><td></td><td><b>Localidade</b></td><td>São Paulo</td><td></td></tr>
                <tr><td></td><td><b>URN</b></td>
                    <td>urn:lex:br;sao.paulo:estadual:lei:2020-01-01;1</td><td></td></tr>
            </table></div>
            </body></html>
        """
        async with respx.mock:
            respx.get(url__startswith="https://www.lexml.gov.br/busca/search").mock(
                return_value=httpx.Response(200, text=html_bad_date),
            )
            async with LexMLPortalCollector(_src()) as c:
                items = await c.collect()
        assert len(items) == 1
        assert items[0].data_publicacao is None  # data inválida tolerada
