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
    DEFAULT_ACCEPT,
    BaseCollector,
    CollectorError,
    RateLimitedError,
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
class TestProxyFallback:
    """Fallback automático via Cloud Function proxy_br em ConnectTimeout."""

    def _geo_src(self) -> Source:
        return Source(
            id="geo-test",
            uf="MG",
            nome="Geo restricted",
            tipo=TipoFonte.ASSEMBLEIA,
            parser=Parser.GENERIC_RSS,
            url="https://www.lexml.gov.br/feed.xml",
            geo_restricted=True,
        )

    @pytest.mark.asyncio
    async def test_no_proxy_no_fallback_on_timeout(self) -> None:
        """Sem proxy configurado: ConnectTimeout sobe (comportamento antigo)."""
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                side_effect=httpx.ConnectTimeout("connect timeout"),
            )
            async with _StubCollector(self._geo_src()) as c:
                with pytest.raises(httpx.ConnectTimeout):
                    await c.fetch()

    @pytest.mark.asyncio
    async def test_proxy_used_on_connect_timeout(self) -> None:
        """ConnectTimeout direto + proxy configurado → re-fetch via proxy."""
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                side_effect=httpx.ConnectTimeout("blocked"),
            )
            respx.get(url__startswith="https://proxy.example.com/").mock(
                return_value=httpx.Response(200, text="<via-proxy/>"),
            )
            collector = _StubCollector(
                self._geo_src(),
                proxy_br_url="https://proxy.example.com/",
                proxy_br_token="secret-token",  # noqa: S106
            )
            async with collector as c:
                text = await c.fetch()
                assert text == "<via-proxy/>"

    @pytest.mark.asyncio
    async def test_proxy_not_used_for_non_geo_sources(self) -> None:
        """Source não-geo: ConnectTimeout sobe mesmo com proxy configurado."""
        non_geo = self._geo_src().model_copy(update={"geo_restricted": False})
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                side_effect=httpx.ConnectTimeout("timeout"),
            )
            collector = _StubCollector(
                non_geo,
                proxy_br_url="https://proxy.example.com/",
                proxy_br_token="secret-token",  # noqa: S106
            )
            async with collector as c:
                with pytest.raises(httpx.ConnectTimeout):
                    await c.fetch()

    @pytest.mark.asyncio
    async def test_proxy_failure_raises_collector_error(self) -> None:
        """Proxy também falha → CollectorError."""
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                side_effect=httpx.ConnectTimeout("blocked"),
            )
            respx.get(url__startswith="https://proxy.example.com/").mock(
                return_value=httpx.Response(502, text="bad gateway"),
            )
            collector = _StubCollector(
                self._geo_src(),
                proxy_br_url="https://proxy.example.com/",
                proxy_br_token="secret-token",  # noqa: S106
            )
            async with collector as c:
                with pytest.raises(CollectorError, match="proxy fetch falhou"):
                    await c.fetch()

    @pytest.mark.asyncio
    async def test_proxy_used_on_403_geo_block(self) -> None:
        """HTTP 403 + geo_restricted + proxy → fallback (geo-block fix)."""
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                return_value=httpx.Response(403, text="forbidden"),
            )
            respx.get(url__startswith="https://proxy.example.com/").mock(
                return_value=httpx.Response(200, text="<via-proxy/>"),
            )
            collector = _StubCollector(
                self._geo_src(),
                proxy_br_url="https://proxy.example.com/",
                proxy_br_token="secret-token",  # noqa: S106
            )
            async with collector as c:
                text = await c.fetch()
                assert text == "<via-proxy/>"

    @pytest.mark.asyncio
    async def test_proxy_used_on_451_unavailable_for_legal(self) -> None:
        """HTTP 451 (UnavailableForLegalReasons) também é geo-block típico."""
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                return_value=httpx.Response(451, text="legal block"),
            )
            respx.get(url__startswith="https://proxy.example.com/").mock(
                return_value=httpx.Response(200, text="ok"),
            )
            collector = _StubCollector(
                self._geo_src(),
                proxy_br_url="https://proxy.example.com/",
                proxy_br_token="secret-token",  # noqa: S106
            )
            async with collector as c:
                text = await c.fetch()
                assert text == "ok"

    @pytest.mark.asyncio
    async def test_403_propaga_quando_nao_geo_restricted(self) -> None:
        """403 sem geo_restricted: HTTPStatusError propaga (sem proxy)."""
        non_geo = self._geo_src().model_copy(update={"geo_restricted": False})
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                return_value=httpx.Response(403, text="forbidden"),
            )
            collector = _StubCollector(
                non_geo,
                proxy_br_url="https://proxy.example.com/",
                proxy_br_token="secret-token",  # noqa: S106
            )
            async with collector as c:
                with pytest.raises(httpx.HTTPStatusError):
                    await c.fetch()

    @pytest.mark.asyncio
    async def test_proxy_used_on_remote_protocol_error(self) -> None:
        """RemoteProtocolError + geo_restricted + proxy → fallback.

        Servidor envia headers HTTP malformados (ex: múltiplos
        Transfer-Encoding) que h11 rejeita por RFC 7230. TJRJ exibiu
        esse comportamento em GH Actions runner US (não local BR).
        """
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                side_effect=httpx.RemoteProtocolError("multiple Transfer-Encoding headers"),
            )
            respx.get(url__startswith="https://proxy.example.com/").mock(
                return_value=httpx.Response(200, text="<via-proxy/>"),
            )
            collector = _StubCollector(
                self._geo_src(),
                proxy_br_url="https://proxy.example.com/",
                proxy_br_token="secret-token",  # noqa: S106
            )
            async with collector as c:
                text = await c.fetch()
                assert text == "<via-proxy/>"

    @pytest.mark.asyncio
    async def test_remote_protocol_error_propaga_sem_geo(self) -> None:
        """RemoteProtocolError sem geo_restricted: erro propaga (sem proxy)."""
        non_geo = self._geo_src().model_copy(update={"geo_restricted": False})
        async with respx.mock:
            respx.get("https://www.lexml.gov.br/feed.xml").mock(
                side_effect=httpx.RemoteProtocolError("malformed headers"),
            )
            collector = _StubCollector(
                non_geo,
                proxy_br_url="https://proxy.example.com/",
                proxy_br_token="secret-token",  # noqa: S106
            )
            async with collector as c:
                with pytest.raises(httpx.RemoteProtocolError):
                    await c.fetch()


@pytest.mark.unit
class TestRateLimitedHandling:
    """429/503 NÃO devem retentar — backoff de 30s não resolve rate limit."""

    @pytest.mark.asyncio
    async def test_429_levanta_rate_limited_error_sem_retry(self) -> None:
        async with respx.mock:
            route = respx.get("https://www.lexml.gov.br/").mock(
                return_value=httpx.Response(429, text="too many requests"),
            )
            async with _StubCollector(_src()) as c:
                with pytest.raises(RateLimitedError, match="429"):
                    await c.fetch()
                # Sem retry: apenas 1 chamada (vs 3 do retry padrão)
                assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_503_levanta_rate_limited_error_sem_retry(self) -> None:
        async with respx.mock:
            route = respx.get("https://www.lexml.gov.br/").mock(
                return_value=httpx.Response(503, text="overloaded"),
            )
            async with _StubCollector(_src()) as c:
                with pytest.raises(RateLimitedError, match="503"):
                    await c.fetch()
                assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_500_continua_com_retry(self) -> None:
        # 500 ainda tenta retry (transient interno do servidor) — só 429/503
        # são considerados rate limit / overload sem retry.
        async with respx.mock:
            route = respx.get("https://www.lexml.gov.br/").mock(
                return_value=httpx.Response(500, text="internal error"),
            )
            async with _StubCollector(_src()) as c:
                with pytest.raises(httpx.HTTPStatusError):
                    await c.fetch()
                # 3 tentativas (RETRY_MAX_ATTEMPTS), sem ser RateLimitedError
                assert route.call_count >= 2  # pelo menos retry uma vez


@pytest.mark.unit
class TestAcceptHeader:
    """Default Accept favorece JSON — fix para sapl-es retornar HTML por default."""

    @pytest.mark.asyncio
    async def test_accept_header_default_inclui_json_primeiro(self) -> None:
        # Verifica que client default tem Accept: application/json...
        async with _StubCollector(_src()) as c:
            assert c._client is not None
            accept = c._client.headers.get("Accept", "")
            assert "application/json" in accept
            # JSON deve vir antes de HTML (preferência)
            assert accept.index("application/json") < accept.index("text/html")

    def test_default_accept_constant_form(self) -> None:
        # Sanity: constante exportada e contém os tipos esperados.
        assert "application/json" in DEFAULT_ACCEPT
        assert "application/xml" in DEFAULT_ACCEPT
        assert "text/html" in DEFAULT_ACCEPT


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
