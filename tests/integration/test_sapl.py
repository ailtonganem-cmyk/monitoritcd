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


class TestDerivePortalBase:
    """`_derive_portal_base` extrai portal a partir de URL de API."""

    def test_derive_com_sapl_subpath(self) -> None:
        from monitoritcd.collectors.custom.sapl import _derive_portal_base  # noqa: PLC0415

        assert (
            _derive_portal_base(
                "https://www.al.ce.leg.br/sapl/api/materia/x/",
            )
            == "https://www.al.ce.leg.br/sapl"
        )

    def test_derive_com_api_no_topo(self) -> None:
        from monitoritcd.collectors.custom.sapl import _derive_portal_base  # noqa: PLC0415

        assert (
            _derive_portal_base(
                "https://sapl.al.ac.leg.br/api/materia/x/",
            )
            == "https://sapl.al.ac.leg.br"
        )

    def test_derive_sem_api_no_path(self) -> None:
        # Linha 190: nem /sapl/api/ nem /api/ -> prefix vazio
        from monitoritcd.collectors.custom.sapl import _derive_portal_base  # noqa: PLC0415

        assert _derive_portal_base("https://example.com/") == "https://example.com"


class TestParseIsoDate:
    """`_parse_iso_date` aceita ISO, retorna None em invalido, defaulta UTC."""

    def test_none_retorna_none(self) -> None:
        from monitoritcd.collectors.custom.sapl import _parse_iso_date  # noqa: PLC0415

        assert _parse_iso_date(None) is None

    def test_string_vazia_retorna_none(self) -> None:
        from monitoritcd.collectors.custom.sapl import _parse_iso_date  # noqa: PLC0415

        assert _parse_iso_date("") is None

    def test_iso_invalido_retorna_none(self) -> None:
        # Linhas 199-200: ValueError de fromisoformat
        from monitoritcd.collectors.custom.sapl import _parse_iso_date  # noqa: PLC0415

        assert _parse_iso_date("not-a-date") is None

    def test_iso_naive_recebe_utc(self) -> None:
        from monitoritcd.collectors.custom.sapl import _parse_iso_date  # noqa: PLC0415

        result = _parse_iso_date("2026-04-25T10:00:00")
        assert result is not None
        assert result.tzinfo is not None  # default UTC

    def test_iso_com_timezone_preserva(self) -> None:
        # Linha 201->203: tzinfo ja presente, nao sobrescreve
        from monitoritcd.collectors.custom.sapl import _parse_iso_date  # noqa: PLC0415

        result = _parse_iso_date("2026-04-25T10:00:00+03:00")
        assert result is not None
        assert result.utcoffset() is not None
        assert result.utcoffset().total_seconds() == 3 * 3600  # type: ignore[union-attr]


class TestParseMateriaInvalido:
    """`_parse_materia` rejeita materia_id nao-int (linha 152)."""

    def test_materia_sem_id_retorna_none(self) -> None:
        from monitoritcd.collectors.custom.sapl import SAPLCollector  # noqa: PLC0415

        c = SAPLCollector(_src())
        result = c._parse_materia(
            {"ementa": "x", "id": "string-em-vez-de-int"},
            portal_base="https://x.gov.br/sapl",
        )
        assert result is None
