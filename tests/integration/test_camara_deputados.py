"""Testes do CamaraDeputadosCollector com fixture JSON da API v2."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from monitoritcd.collectors import CamaraDeputadosCollector
from monitoritcd.core.base_collector import _DomainRateLimiter
from monitoritcd.core.models import Parser, Source, TipoFonte


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    _DomainRateLimiter._reset_for_tests()


def _src() -> Source:
    return Source(
        id="camara-test",
        uf="_federal",
        nome="Camara Deputados",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.CAMARA_DEPUTADOS,
        url="https://dadosabertos.camara.leg.br/api/v2/proposicoes",
        selectors={"palavras_chave": "ITCMD", "dias": "30000", "page_size": "5"},
    )


CAMARA_RESPONSE = json.dumps(
    {
        "dados": [
            {
                "id": 2613074,
                "uri": "https://dadosabertos.camara.leg.br/api/v2/proposicoes/2613074",
                "siglaTipo": "PLP",
                "codTipo": 140,
                "numero": 86,
                "ano": 2026,
                "ementa": "Altera a Lei Complementar 227/2026 sobre ITCMD.",
                "dataApresentacao": "2026-04-01T11:03",
            },
            {
                "id": 2500000,
                "siglaTipo": "PEC",
                "numero": 45,
                "ano": 2019,
                "ementa": "Reforma Tributária — institui IBS/ITBI/ITCMD.",
                "dataApresentacao": "2019-04-03T10:00",
            },
        ],
        "links": [{"rel": "self", "href": "..."}],
    }
)


@pytest.mark.integration
class TestCamaraDeputadosCollector:
    @pytest.mark.asyncio
    async def test_parses_response(self) -> None:
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.camara.leg.br/").mock(
                return_value=httpx.Response(200, text=CAMARA_RESPONSE),
            )
            async with CamaraDeputadosCollector(_src()) as c:
                items = await c.collect()
        assert len(items) == 2
        assert items[0].titulo_raw == "PLP 86/2026"
        assert items[0].url == (
            "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2613074"
        )
        assert "ITCMD" in (items[0].texto_raw or "")
        assert items[0].data_publicacao is not None
        assert items[0].data_publicacao.year == 2026

    @pytest.mark.asyncio
    async def test_dedupe_across_keywords(self) -> None:
        # 3 keywords retornam mesma fixture → dedup por id retorna 2
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "ITCMD|ITCD|sucessão",
                    "dias": "30000",
                    "page_size": "5",
                },
            },
        )
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.camara.leg.br/").mock(
                return_value=httpx.Response(200, text=CAMARA_RESPONSE),
            )
            async with CamaraDeputadosCollector(src) as c:
                items = await c.collect()
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_filter_by_dias(self) -> None:
        # PEC 45/2019 e PLP 86/2026; dias=1 ainda mantem o de 2026 (depende do cutoff)
        # Mas com fixture forcando datas antigas, filtra ambos
        old_resp = json.dumps(
            {
                "dados": [
                    {
                        "id": 1,
                        "siglaTipo": "PL",
                        "numero": 1,
                        "ano": 2019,
                        "ementa": "ITCMD",
                        "dataApresentacao": "2019-04-03T10:00",
                    },
                ],
            }
        )
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "ITCMD",
                    "dias": "1",
                    "page_size": "5",
                },
            },
        )
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.camara.leg.br/").mock(
                return_value=httpx.Response(200, text=old_resp),
            )
            async with CamaraDeputadosCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_invalid_json_continues(self) -> None:
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.camara.leg.br/").mock(
                return_value=httpx.Response(200, text="not json"),
            )
            async with CamaraDeputadosCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_empty_keywords_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(update={"selectors": {"palavras_chave": "  |  "}})
        async with CamaraDeputadosCollector(src) as c:
            with pytest.raises(CollectorError, match="palavras_chave"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_dias_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "dias": "abc"}},
        )
        async with CamaraDeputadosCollector(src) as c:
            with pytest.raises(CollectorError, match="dias"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_page_size_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "page_size": "abc"}},
        )
        async with CamaraDeputadosCollector(src) as c:
            with pytest.raises(CollectorError, match="page_size"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_skips_item_without_id(self) -> None:
        bad = json.dumps({"dados": [{"siglaTipo": "PL", "ementa": "no id"}]})
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.camara.leg.br/").mock(
                return_value=httpx.Response(200, text=bad),
            )
            async with CamaraDeputadosCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_failure_continues(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.camara.leg.br/").mock(
                side_effect=CollectorError("simulated"),
            )
            async with CamaraDeputadosCollector(_src()) as c:
                items = await c.collect()
        assert items == []


class TestParseHelpers:
    def test_parse_proposicao_id_nao_int(self) -> None:
        c = CamaraDeputadosCollector(_src())
        assert c._parse_proposicao({"id": "string"}) is None
        assert c._parse_proposicao({"id": None}) is None
        assert c._parse_proposicao({}) is None

    def test_parse_iso_date_helper(self) -> None:
        from monitoritcd.collectors.custom.camara_deputados import _parse_iso_date  # noqa: PLC0415

        assert _parse_iso_date(None) is None
        assert _parse_iso_date("") is None
        assert _parse_iso_date("invalid") is None
        d = _parse_iso_date("2026-04-01T11:03")
        assert d is not None and d.tzinfo is not None
        d2 = _parse_iso_date("2026-04-01T11:03+02:00")
        assert d2 is not None
        assert d2.utcoffset().total_seconds() == 2 * 3600  # type: ignore[union-attr]
