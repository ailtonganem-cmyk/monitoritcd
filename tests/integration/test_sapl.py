"""Testes do SAPLCollector com fixture JSON.

SAPL = Sistema de Apoio ao Processo Legislativo (Interlegis).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from monitoritcd.collectors import SAPLCollector
from monitoritcd.core.base_collector import _DomainRateLimiter
from monitoritcd.core.models import Parser, Source, TipoFonte


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    _DomainRateLimiter._reset_for_tests()


def _src(url: str = "https://sapl.al.ac.leg.br/api/materia/materialegislativa/") -> Source:
    return Source(
        id="sapl-test",
        uf="AC",
        nome="SAPL Test",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.SAPL,
        url=url,
        selectors={
            "palavras_chave": "ITCMD",
            "dias": "3650",
            "page_size": "5",
        },
    )


SAPL_RESPONSE = json.dumps(
    {
        "pagination": {"total_entries": 1, "total_pages": 1, "page": 1},
        "results": [
            {
                "id": 18729,
                "__str__": "Projeto de Lei nº 49 de 2024",
                "link_detail_backend": "/materia/18729",
                "numero": 49,
                "ano": 2024,
                "data_apresentacao": "2024-03-15",
                "ementa": "Dispõe sobre isenção de ITCMD para herança até R$ 50 mil.",
                "em_tramitacao": True,
                "tipo": 1,
            },
        ],
    }
)


@pytest.mark.integration
class TestSAPLCollector:
    @pytest.mark.asyncio
    async def test_parses_response(self) -> None:
        async with respx.mock:
            respx.get(url__startswith="https://sapl.al.ac.leg.br/").mock(
                return_value=httpx.Response(200, text=SAPL_RESPONSE),
            )
            async with SAPLCollector(_src()) as c:
                items = await c.collect()
        assert len(items) == 1
        assert "Projeto de Lei nº 49" in items[0].titulo_raw
        assert items[0].url == "https://sapl.al.ac.leg.br/materia/18729"
        assert items[0].data_publicacao is not None
        assert items[0].data_publicacao.year == 2024
        assert "ITCMD" in (items[0].texto_raw or "")

    @pytest.mark.asyncio
    async def test_dedupe_across_keywords(self) -> None:
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "ITCMD|ITCD|sucessão",
                    "dias": "3650",
                    "page_size": "5",
                },
            },
        )
        async with respx.mock:
            respx.get(url__startswith="https://sapl.al.ac.leg.br/").mock(
                return_value=httpx.Response(200, text=SAPL_RESPONSE),
            )
            async with SAPLCollector(src) as c:
                items = await c.collect()
        # 3 keywords, mesma resposta → dedup por id retorna 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_filter_by_dias(self) -> None:
        # data_apresentacao 2024-03-15; dias=1 → muito antigo, descarta
        src = _src().model_copy(
            update={
                "selectors": {"palavras_chave": "ITCMD", "dias": "1", "page_size": "5"},
            },
        )
        async with respx.mock:
            respx.get(url__startswith="https://sapl.al.ac.leg.br/").mock(
                return_value=httpx.Response(200, text=SAPL_RESPONSE),
            )
            async with SAPLCollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_invalid_json_continues(self) -> None:
        async with respx.mock:
            respx.get(url__startswith="https://sapl.al.ac.leg.br/").mock(
                return_value=httpx.Response(200, text="not json"),
            )
            async with SAPLCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_empty_keywords_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "  |  "}},
        )
        async with SAPLCollector(src) as c:
            with pytest.raises(CollectorError, match="palavras_chave"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_dias_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "dias": "abc"}},
        )
        async with SAPLCollector(src) as c:
            with pytest.raises(CollectorError, match="dias"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_page_size_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "ITCMD", "page_size": "abc"}},
        )
        async with SAPLCollector(src) as c:
            with pytest.raises(CollectorError, match="page_size"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_missing_id_skipped(self) -> None:
        bad_response = json.dumps({"results": [{"ementa": "no id"}]})
        async with respx.mock:
            respx.get(url__startswith="https://sapl.al.ac.leg.br/").mock(
                return_value=httpx.Response(200, text=bad_response),
            )
            async with SAPLCollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_portal_base_with_sapl_subpath(self) -> None:
        """Quando a URL é www.al.ce.leg.br/sapl/api/..., portal_base deve preservar /sapl."""
        src = Source(
            id="sapl-ce",
            uf="CE",
            nome="ALECE SAPL",
            tipo=TipoFonte.ASSEMBLEIA,
            parser=Parser.SAPL,
            url="https://www.al.ce.leg.br/sapl/api/materia/materialegislativa/",
            selectors={"palavras_chave": "ITCMD", "dias": "3650"},
        )
        async with respx.mock:
            respx.get(url__startswith="https://www.al.ce.leg.br/").mock(
                return_value=httpx.Response(200, text=SAPL_RESPONSE),
            )
            async with SAPLCollector(src) as c:
                items = await c.collect()
        assert len(items) == 1
        assert items[0].url == "https://www.al.ce.leg.br/sapl/materia/18729"

    @pytest.mark.asyncio
    async def test_fetch_failure_continues(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        async with respx.mock:
            respx.get(url__startswith="https://sapl.al.ac.leg.br/").mock(
                side_effect=CollectorError("simulated"),
            )
            async with SAPLCollector(_src()) as c:
                items = await c.collect()
        assert items == []
