"""Testes do ALEPECollector com fixture XML real (580KB, ALEPE 2025)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from monitoritcd.collectors import ALEPECollector
from monitoritcd.core.base_collector import _DomainRateLimiter
from monitoritcd.core.models import Parser, Source, TipoFonte

FIXTURE = Path(__file__).parent.parent / "fixtures" / "alepe_projetos_2025.xml"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    _DomainRateLimiter._reset_for_tests()


def _src() -> Source:
    return Source(
        id="alepe-test",
        uf="PE",
        nome="ALEPE",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.ALEPE,
        url="https://dadosabertos.alepe.pe.gov.br/api/v1/proposicoes",
        selectors={
            "palavras_chave": "doação",
            "dias": "30000",
            "tipos": "projetos",
        },
    )


@pytest.mark.integration
class TestALEPECollector:
    @pytest.mark.asyncio
    async def test_parses_real_fixture(self) -> None:
        xml = FIXTURE.read_text(encoding="utf-8")
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.alepe.pe.gov.br/").mock(
                return_value=httpx.Response(200, text=xml),
            )
            async with ALEPECollector(_src()) as c:
                items = await c.collect()
        # Fixture tem ~945 projetos; "doação" deve ter alguns hits
        assert len(items) >= 1
        # Confirma estrutura
        for it in items[:3]:
            assert it.titulo_raw
            assert "alepe.pe.gov.br/proposicoes/" in it.url
            assert "doa" in (it.texto_raw or "").lower()

    @pytest.mark.asyncio
    async def test_filter_by_dias(self) -> None:
        # dias=1 → todos os projetos do fixture (2025) ficam fora
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "doação",
                    "dias": "1",
                    "tipos": "projetos",
                },
            },
        )
        xml = FIXTURE.read_text(encoding="utf-8")
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.alepe.pe.gov.br/").mock(
                return_value=httpx.Response(200, text=xml),
            )
            async with ALEPECollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_keyword_local_filter(self) -> None:
        # Termo absurdo → 0 hits (filtro local)
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "NUNCAEXISTIRA_TOKEN_ABSURDO",
                    "dias": "30000",
                    "tipos": "projetos",
                },
            },
        )
        xml = FIXTURE.read_text(encoding="utf-8")
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.alepe.pe.gov.br/").mock(
                return_value=httpx.Response(200, text=xml),
            )
            async with ALEPECollector(src) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_dedupe_across_anos_e_tipos(self) -> None:
        # 2 tipos x 2 anos = 4 requests; fixture mesma -> dedup por docid
        src = _src().model_copy(
            update={
                "selectors": {
                    "palavras_chave": "doação",
                    "dias": "30000",
                    "tipos": "projetos|indicacoes",
                },
            },
        )
        xml = FIXTURE.read_text(encoding="utf-8")
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.alepe.pe.gov.br/").mock(
                return_value=httpx.Response(200, text=xml),
            )
            async with ALEPECollector(src) as c:
                items = await c.collect()
        # Mesmo retornando 4x, dedup por docid garante ≤ N único
        ids = {it.content_hash for it in items}
        assert len(ids) == len(items)

    @pytest.mark.asyncio
    async def test_empty_keywords_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(update={"selectors": {"palavras_chave": "  |  "}})
        async with ALEPECollector(src) as c:
            with pytest.raises(CollectorError, match="palavras_chave"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_invalid_dias_raises(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        src = _src().model_copy(
            update={"selectors": {"palavras_chave": "doação", "dias": "abc"}},
        )
        async with ALEPECollector(src) as c:
            with pytest.raises(CollectorError, match="dias"):
                await c.collect()

    @pytest.mark.asyncio
    async def test_fetch_failure_continues(self) -> None:
        from monitoritcd.core.base_collector import CollectorError  # noqa: PLC0415

        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.alepe.pe.gov.br/").mock(
                side_effect=CollectorError("simulated"),
            )
            async with ALEPECollector(_src()) as c:
                items = await c.collect()
        assert items == []

    @pytest.mark.asyncio
    async def test_xml_without_docid_skipped(self) -> None:
        bad_xml = "<projetos><projeto numero='1'/><projeto docid='X' ementa='doação x'/></projetos>"
        async with respx.mock:
            respx.get(url__startswith="https://dadosabertos.alepe.pe.gov.br/").mock(
                return_value=httpx.Response(200, text=bad_xml),
            )
            async with ALEPECollector(_src()) as c:
                items = await c.collect()
        # Sem dataPublicacao válida → cutoff filter desabilitado para esse → passa
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_invalid_date_returns_none(self) -> None:
        from monitoritcd.collectors.custom.alepe import _parse_date_br  # noqa: PLC0415

        assert _parse_date_br(None) is None
        assert _parse_date_br("") is None
        assert _parse_date_br("2025-01-01") is None  # ISO, não BR
        assert _parse_date_br("32/13/2025") is None  # data inválida
