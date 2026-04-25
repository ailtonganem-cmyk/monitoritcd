"""Testes do ALEPCollector com fixture JSON."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from monitoritcd.collectors import ALEPCollector
from monitoritcd.core.base_collector import _DomainRateLimiter
from monitoritcd.core.models import Parser, Source, TipoFonte


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    _DomainRateLimiter._reset_for_tests()


def _src() -> Source:
    return Source(
        id="alep-test",
        uf="PR",
        nome="ALEP",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.ALEP,
        url="http://webservices.assembleia.pr.leg.br/api/public/proposicao/filtrar",
        selectors={"palavras_chave": "ITCMD", "dias": "30000", "quantidade": "5"},
    )


ALEP_RESPONSE = json.dumps(
    {
        "sucesso": True,
        "erro": None,
        "lista": [
            {
                "codigo": 14908,
                "numero": 14,
                "ano": 2006,
                "autor": "MARCOS ISFER",
                "dataRecebimento": "2006-02-17T08:00:00.000+0000",
                "tipoProposicao": "PROJETO DE LEI",
                "ementa": "Dispensa pagamento de ITCMD para carentes.",
                "status": "ARQUIVADA",
                "localAtual": "ARQUIVADO",
            },
        ],
    }
)


@pytest.mark.integration
class TestALEPCollector:
    @pytest.mark.asyncio
    async def test_parses_response(self) -> None:
        async with respx.mock:
            respx.post(
                "http://webservices.assembleia.pr.leg.br/api/public/proposicao/filtrar"
            ).mock(return_value=httpx.Response(200, text=ALEP_RESPONSE))
            async with ALEPCollector(_src()) as c:
                items = await c.collect()
        assert len(items) == 1
        assert "PROJETO DE LEI 14/2006" in items[0].titulo_raw
        assert items[0].data_publicacao is not None
        assert items[0].data_publicacao.year == 2006
        assert "ITCMD" in (items[0].texto_raw or "")
        assert items[0].url == "https://www.assembleia.pr.leg.br/proposicao?id=14908"

    @pytest.mark.asyncio
    async def test_dedupe_across_keywords(self) -> None:
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "ITCMD|ITCD|sucessão",
                    "dias": "30000",
                    "quantidade": "5",
                },
            },
        )
        async with respx.mock:
            respx.post(
                "http://webservices.assembleia.pr.leg.br/api/public/proposicao/filtrar"
            ).mock(return_value=httpx.Response(200, text=ALEP_RESPONSE))
            async with ALEPCollector(src) as c:
                items = await c.collect()
        # 3 keywords, mesma response → dedup por codigo retorna 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_filter_by_dias(self) -> None:
        # Item de 2006; dias=1 (filtra)
        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "dias": "1", "quantidade": "5"}},
        )
        async with respx.mock:
            respx.post(
                "http://webservices.assembleia.pr.leg.br/api/public/proposicao/filtrar"
            ).mock(return_value=httpx.Response(200, text=ALEP_RESPONSE))
            async with ALEPCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_sucesso_false_logs_and_continues(self) -> None:
        bad = json.dumps({"sucesso": False, "erro": "rate limit", "lista": []})
        async with respx.mock:
            respx.post(
                "http://webservices.assembleia.pr.leg.br/api/public/proposicao/filtrar"
            ).mock(return_value=httpx.Response(200, text=bad))
            async with ALEPCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_invalid_json_continues(self) -> None:
        async with respx.mock:
            respx.post(
                "http://webservices.assembleia.pr.leg.br/api/public/proposicao/filtrar"
            ).mock(return_value=httpx.Response(200, text="<html>error</html>"))
            async with ALEPCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_empty_keywords_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(update={"selectors": {"palavras_chave": "  |  "}})
        async with ALEPCollector(src) as c:
            with pytest.raises(CollectorError, match="palavras_chave"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_dias_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "dias": "abc"}},
        )
        async with ALEPCollector(src) as c:
            with pytest.raises(CollectorError, match="dias"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_quantidade_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "quantidade": "abc"}},
        )
        async with ALEPCollector(src) as c:
            with pytest.raises(CollectorError, match="quantidade"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_skips_item_without_codigo(self) -> None:
        bad = json.dumps({"sucesso": True, "lista": [{"ementa": "no code"}]})
        async with respx.mock:
            respx.post(
                "http://webservices.assembleia.pr.leg.br/api/public/proposicao/filtrar"
            ).mock(return_value=httpx.Response(200, text=bad))
            async with ALEPCollector(_src()) as c:
                items = await c.collect()
        assert items == []
