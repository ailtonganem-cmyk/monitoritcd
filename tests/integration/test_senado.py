"""Testes do SenadoCollector com fixture JSON da API /processo."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from monitoritcd.collectors import SenadoCollector
from monitoritcd.core.base_collector import _DomainRateLimiter
from monitoritcd.core.models import Parser, Source, TipoFonte


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    _DomainRateLimiter._reset_for_tests()


def _src() -> Source:
    return Source(
        id="senado-test",
        uf="_federal",
        nome="Senado Federal",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.SENADO,
        url="https://legis.senado.leg.br/dadosabertos/processo",
        selectors={"palavras_chave": "ITCMD", "dias": "30000", "page_size": "5"},
    )


# Resposta no formato lista no top-level (observado no WebFetch real)
SENADO_RESPONSE = json.dumps(
    [
        {
            "identificacao": "VET 8/2026",
            "ementa": "Veto parcial à LC sobre ITCMD e Comitê Gestor IBS.",
            "dataApresentacao": "2026-01-14",
            "tipoDocumento": "Veto",
            "tramitando": True,
            "casaIdentificadora": "SF",
            "codigoMateria": 161234,
        },
        {
            "identificacao": "PLS 100/2024",
            "ementa": "Sucessão hereditária digital — bens cripto.",
            "dataApresentacao": "2024-05-10",
            "tipoDocumento": "Projeto de Lei do Senado",
            "tramitando": True,
        },
    ]
)


@pytest.mark.integration
class TestSenadoCollector:
    @pytest.mark.asyncio
    async def test_parses_response(self) -> None:
        # Usa 2 keywords para cobrir os 2 items do fixture (ITCMD e sucessão)
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "ITCMD|sucessão",
                    "dias": "30000",
                    "page_size": "5",
                },
            },
        )
        async with respx.mock:
            respx.get(url__startswith="https://legis.senado.leg.br/").mock(
                return_value=httpx.Response(200, text=SENADO_RESPONSE),
            )
            async with SenadoCollector(src) as c:
                items = await c.collect()
        assert len(items) == 2
        # Items vêm na ordem das keywords e do fixture
        titulos = [i.titulo_raw for i in items]
        assert any("VET 8/2026" in t for t in titulos)
        assert any("PLS 100/2024" in t for t in titulos)
        # Item com codigoMateria usa URL canonica /materia/{id}
        veto = next(i for i in items if "VET" in i.titulo_raw)
        assert "/materia/161234" in veto.url
        # Item sem codigoMateria usa URL de busca encoded
        pls = next(i for i in items if "PLS" in i.titulo_raw)
        assert "busca=PLS" in pls.url and "100" in pls.url

    @pytest.mark.asyncio
    async def test_filtro_local_por_keyword(self) -> None:
        # Caso a API ignore palavraChave: filter local descarta fora-de-tema
        resp = json.dumps(
            [
                {
                    "identificacao": "PLS 50/2024",
                    "ementa": "Crédito agrícola para pequenos produtores.",
                    "dataApresentacao": "2024-01-01",
                    "tipoDocumento": "PLS",
                },
                {
                    "identificacao": "PLS 51/2024",
                    "ementa": "ITCMD em planos de previdência privada.",
                    "dataApresentacao": "2024-01-02",
                    "tipoDocumento": "PLS",
                },
            ]
        )
        async with respx.mock:
            respx.get(url__startswith="https://legis.senado.leg.br/").mock(
                return_value=httpx.Response(200, text=resp),
            )
            async with SenadoCollector(_src()) as c:
                items = await c.collect()
        # Apenas o segundo item passa pelo filtro local de "ITCMD"
        assert len(items) == 1
        assert "PLS 51/2024" in items[0].titulo_raw

    @pytest.mark.asyncio
    async def test_resposta_envelopada_em_records(self) -> None:
        # API pode retornar {records: [...]} em vez de lista direta
        wrapped = json.dumps({"records": [json.loads(SENADO_RESPONSE)[0]]})
        async with respx.mock:
            respx.get(url__startswith="https://legis.senado.leg.br/").mock(
                return_value=httpx.Response(200, text=wrapped),
            )
            async with SenadoCollector(_src()) as c:
                items = await c.collect()
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_invalid_json_continues(self) -> None:
        async with respx.mock:
            respx.get(url__startswith="https://legis.senado.leg.br/").mock(
                return_value=httpx.Response(200, text="not json"),
            )
            async with SenadoCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_empty_keywords_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(update={"selectors": {"palavras_chave": "  |  "}})
        async with SenadoCollector(src) as c:
            with pytest.raises(CollectorError, match="palavras_chave"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_dias_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "dias": "abc"}},
        )
        async with SenadoCollector(src) as c:
            with pytest.raises(CollectorError, match="dias"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_page_size_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "page_size": "abc"}},
        )
        async with SenadoCollector(src) as c:
            with pytest.raises(CollectorError, match="page_size"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_filter_by_dias(self) -> None:
        old = json.dumps(
            [
                {
                    "identificacao": "PLS 1/2010",
                    "ementa": "ITCMD",
                    "dataApresentacao": "2010-01-01",
                    "tipoDocumento": "PLS",
                },
            ]
        )
        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "dias": "1"}},
        )
        async with respx.mock:
            respx.get(url__startswith="https://legis.senado.leg.br/").mock(
                return_value=httpx.Response(200, text=old),
            )
            async with SenadoCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_failure_continues(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        async with respx.mock:
            respx.get(url__startswith="https://legis.senado.leg.br/").mock(
                side_effect=CollectorError("simulated"),
            )
            async with SenadoCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_skips_item_without_identificacao(self) -> None:
        bad = json.dumps([{"ementa": "ITCMD x", "dataApresentacao": "2026-01-01"}])
        async with respx.mock:
            respx.get(url__startswith="https://legis.senado.leg.br/").mock(
                return_value=httpx.Response(200, text=bad),
            )
            async with SenadoCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_dedupe_across_keywords(self) -> None:
        # 1 request único cobrindo N keywords; cada item passa se QUALQUER keyword bate.
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "ITCMD|sucessão",
                    "dias": "30000",
                    "page_size": "5",
                },
            },
        )
        async with respx.mock:
            route = respx.get(url__startswith="https://legis.senado.leg.br/").mock(
                return_value=httpx.Response(200, text=SENADO_RESPONSE),
            )
            async with SenadoCollector(src) as c:
                items = await c.collect()
        # ITCMD: VET 8/2026 (ementa); sucessão: PLS 100/2024 (ementa)
        assert len(items) == 2
        # Otimização: 1 request único independente de N keywords
        assert route.call_count == 1


class TestExtractRecords:
    """`_extract_records` aceita variantes de formato top-level."""

    def test_lista_direta(self) -> None:
        from monitoritcd.collectors.custom.senado import _extract_records  # noqa: PLC0415

        assert _extract_records([{"a": 1}]) == [{"a": 1}]

    def test_dict_com_records(self) -> None:
        from monitoritcd.collectors.custom.senado import _extract_records  # noqa: PLC0415

        assert _extract_records({"records": [{"a": 1}]}) == [{"a": 1}]

    def test_dict_com_data(self) -> None:
        from monitoritcd.collectors.custom.senado import _extract_records  # noqa: PLC0415

        assert _extract_records({"data": [{"x": 2}]}) == [{"x": 2}]

    def test_tipo_inesperado_retorna_vazio(self) -> None:
        from monitoritcd.collectors.custom.senado import _extract_records  # noqa: PLC0415

        assert _extract_records("string") == []
        assert _extract_records(None) == []
        assert _extract_records({"unknown_key": [{"a": 1}]}) == []

    def test_filtra_nao_dicts(self) -> None:
        from monitoritcd.collectors.custom.senado import _extract_records  # noqa: PLC0415

        assert _extract_records([{"a": 1}, "string", 42, {"b": 2}]) == [
            {"a": 1},
            {"b": 2},
        ]


class TestParseHelpers:
    def test_parse_processo_sem_identificacao(self) -> None:
        c = SenadoCollector(_src())
        assert c._parse_processo({"ementa": "x"}) is None
        assert c._parse_processo({"identificacao": ""}) is None
        assert c._parse_processo({"identificacao": 123}) is None  # type: ignore[arg-type]

    def test_parse_iso_date_helper(self) -> None:
        from monitoritcd.collectors.custom.senado import _parse_iso_date  # noqa: PLC0415

        assert _parse_iso_date(None) is None
        assert _parse_iso_date("") is None
        assert _parse_iso_date("invalid") is None
        d = _parse_iso_date("2026-04-25")
        assert d is not None and d.tzinfo is not None
        d2 = _parse_iso_date("2026-04-25T10:00:00+02:00")
        assert d2 is not None
        assert d2.utcoffset().total_seconds() == 2 * 3600  # type: ignore[union-attr]
