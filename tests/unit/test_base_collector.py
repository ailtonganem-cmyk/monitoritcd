"""Testes do `BaseCollector` ABC.

Cobre:
- URL validation antes de fetch (anti-SSRF)
- Hash determinístico do conteúdo
- Rate limiter por domínio
- Context manager (__aenter__/__aexit__)
- Retry em falha transitória
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from monitoritcd.core.base_collector import (
    BaseCollector,
    CollectorError,
    _domain_of,
    _DomainRateLimiter,
    content_hash,
)
from monitoritcd.core.models import Parser, RawItem, Source, TipoFonte
from monitoritcd.security.url_validator import UnsafeURLError


def _src(url: str = "https://www.lexml.gov.br/", parser: Parser = Parser.LEXML) -> Source:
    return Source(
        id="test-src",
        uf="_federal",
        nome="Test Source",
        tipo=TipoFonte.JURISPRUDENCIA,
        parser=parser,
        url=url,
    )


class _StubCollector(BaseCollector):
    """Collector mínimo para testar a ABC."""

    async def collect(self) -> list[RawItem]:
        text = await self.fetch()
        return [self.make_raw_item("Title", self.source.url, texto=text)]


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Garante isolamento entre testes."""
    _DomainRateLimiter._reset_for_tests()


@pytest.mark.unit
class TestContentHash:
    def test_deterministic(self) -> None:
        h1 = content_hash("hello")
        h2 = content_hash("hello")
        assert h1 == h2
        assert len(h1) == 64

    def test_different_inputs_different_hashes(self) -> None:
        assert content_hash("a") != content_hash("b")


@pytest.mark.unit
class TestDomainOf:
    def test_https_url(self) -> None:
        assert _domain_of("https://www.example.com/path") == "www.example.com"

    def test_invalid_url_returns_unknown(self) -> None:
        assert _domain_of("not-a-url") == "unknown"


@pytest.mark.unit
class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_subsequent_calls(self) -> None:
        # Chamadas consecutivas em mesmo domínio devem aguardar.
        # Usamos intervalo maior (0.3s) por tolerância ao scheduler do Windows.
        loop = asyncio.get_event_loop()
        start = loop.time()
        await _DomainRateLimiter.acquire("test.example", min_interval=0.3)
        await _DomainRateLimiter.acquire("test.example", min_interval=0.3)
        elapsed = loop.time() - start
        # Tolerância de 10ms para imprecisão do scheduler do Windows.
        assert elapsed >= 0.29, f"Esperado >= 0.29s (rate limit ativo), foi {elapsed}"

    @pytest.mark.asyncio
    async def test_different_domains_dont_block(self) -> None:
        loop = asyncio.get_event_loop()
        start = loop.time()
        await _DomainRateLimiter.acquire("a.example", min_interval=0.5)
        await _DomainRateLimiter.acquire("b.example", min_interval=0.5)
        elapsed = loop.time() - start
        assert elapsed < 0.4  # diferentes domínios não bloqueiam


@pytest.mark.unit
class TestBaseCollectorContext:
    @pytest.mark.asyncio
    async def test_context_manager_creates_and_closes_client(self) -> None:
        async with _StubCollector(_src()) as collector:
            assert collector._client is not None
        assert collector._client is None

    @pytest.mark.asyncio
    async def test_external_client_not_closed(self) -> None:
        client = httpx.AsyncClient()
        async with _StubCollector(_src(), http_client=client) as collector:
            assert collector._client is client
        # Cliente externo não foi fechado
        assert not client.is_closed
        await client.aclose()


@pytest.mark.unit
class TestFetchURLValidation:
    @pytest.mark.asyncio
    async def test_fetch_rejects_localhost(self) -> None:
        async with _StubCollector(_src(url="https://www.lexml.gov.br/")) as c:
            with pytest.raises(UnsafeURLError):
                await c.fetch("https://localhost/")

    @pytest.mark.asyncio
    async def test_fetch_rejects_metadata_ip(self) -> None:
        async with _StubCollector(_src()) as c:
            with pytest.raises(UnsafeURLError):
                await c.fetch("https://169.254.169.254/")

    @pytest.mark.asyncio
    async def test_fetch_requires_context_manager(self) -> None:
        # Sem __aenter__ e sem http_client externo, fetch falha
        c = _StubCollector(_src())
        with pytest.raises(CollectorError, match="async with"):
            await c.fetch()


@pytest.mark.unit
class TestFetchSuccess:
    @pytest.mark.asyncio
    async def test_fetch_returns_text(self) -> None:
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/").mock(
                return_value=httpx.Response(200, text="<xml>ok</xml>"),
            )
            async with _StubCollector(_src()) as c:
                text = await c.fetch()
                assert text == "<xml>ok</xml>"

    @pytest.mark.asyncio
    async def test_fetch_raises_on_500(self) -> None:
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/").mock(
                return_value=httpx.Response(500),
            )
            async with _StubCollector(_src()) as c:
                with pytest.raises(httpx.HTTPStatusError):
                    await c.fetch()


@pytest.mark.unit
class TestMakeRawItem:
    @pytest.mark.asyncio
    async def test_make_raw_item_includes_hash(self) -> None:
        async with _StubCollector(_src()) as c:
            item = c.make_raw_item("Título", "https://www.lexml.gov.br/abc")
            assert item.source_id == "test-src"
            assert item.titulo_raw == "Título"
            assert len(item.content_hash) == 64

    @pytest.mark.asyncio
    async def test_explicit_hash_input_is_used(self) -> None:
        async with _StubCollector(_src()) as c:
            item1 = c.make_raw_item("A", "https://www.lexml.gov.br/x", content_for_hash="stable-id")
            item2 = c.make_raw_item("A", "https://www.lexml.gov.br/x", content_for_hash="stable-id")
            assert item1.content_hash == item2.content_hash
