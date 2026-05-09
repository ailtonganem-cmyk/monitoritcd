"""ABC para todos os coletores.

Padrão:
    async with MyCollector(source) as collector:
        items = await collector.collect()

Garantias da `BaseCollector`:
- URL validada anti-SSRF antes de toda requisição.
- Rate limit por domínio (≥ 2s entre requests ao mesmo host).
- Retry exponencial em falhas transitórias (até 3 tentativas).
- Timeout de 30s/request.
- User-Agent identificável (boa cidadania na coleta).
- Hash SHA-256 do conteúdo para dedup.

Princípios canônicos aplicados:
1. URL externa NÃO é confiável — `validate_url` antes de fetch.
2. `MAX_HTML_BYTES` enforcement no consumidor (collectors que armazenam HTML).
3. Mensagens de erro genéricas para fora; detalhe técnico no log estruturado.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar, Final, Self
from urllib.parse import urlparse

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from monitoritcd.core import limits
from monitoritcd.core.models import RawItem
from monitoritcd.security.url_validator import validate_url

if TYPE_CHECKING:
    from types import TracebackType

    from monitoritcd.core.models import Source

USER_AGENT: Final[str] = "MonitorITCD/0.1 (+https://github.com/monitoritcd; ITCD legal monitor)"

# Accept JSON-first; fontes que servem JSON+HTML respeitam Content Negotiation
# e devolvem JSON quando explicitamente pedido. Fix para sapl-es que retornava
# HTML por default.
DEFAULT_ACCEPT: Final[str] = "application/json, application/xml;q=0.9, text/html;q=0.5, */*;q=0.1"

# Status HTTP que disparam fallback via proxy_br para fontes geo_restricted.
# 403 Forbidden tipicamente indica geo-block; 451 indica conteúdo restrito por
# motivos legais (também geo-bloqueio em alguns casos).
GEO_BLOCK_STATUS: Final[frozenset[int]] = frozenset({403, 451})

# Status que NÃO devem fazer retry interno: rate limit (429) e server overload
# (503). Retry exponencial de 30s não resolve esses casos — servidor precisa
# de janela maior. Marcar como falha transient e tentar próxima execução.
NO_RETRY_STATUS: Final[frozenset[int]] = frozenset({429, 503})

logger = structlog.get_logger(__name__)


class CollectorError(Exception):
    """Erro durante coleta. Captura no orquestrador para isolar fontes."""


class RateLimitedError(CollectorError):
    """Servidor retornou 429/503 — não retentar nesta execução."""


class _DomainRateLimiter:
    """Rate limiter por domínio usando asyncio.Lock + monotonic clock.

    Singleton de classe — compartilhado entre coletores no mesmo processo.
    Em testes, usar domains distintos para isolamento.
    """

    _locks: ClassVar[dict[str, asyncio.Lock]] = {}
    _last_request: ClassVar[dict[str, float]] = {}

    @classmethod
    async def acquire(cls, domain: str, min_interval: float) -> None:
        """Espera até poder fazer request a este domain."""
        if domain not in cls._locks:
            cls._locks[domain] = asyncio.Lock()
        async with cls._locks[domain]:
            now = time.monotonic()
            elapsed = now - cls._last_request.get(domain, 0.0)
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            cls._last_request[domain] = time.monotonic()

    @classmethod
    def _reset_for_tests(cls) -> None:
        """Limpa estado — uso EXCLUSIVO de testes."""
        cls._locks.clear()
        cls._last_request.clear()


def _domain_of(url: str) -> str:
    return urlparse(url).hostname or "unknown"


def content_hash(content: str) -> str:
    """SHA-256 hex de uma string. Usado para dedup e cache de classificação."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class BaseCollector(ABC):
    """Abstract base para coletores.

    Subclasses implementam `collect()`, retornando `list[RawItem]`.
    Use sempre como context manager (`async with`) para garantir cleanup do client.
    """

    def __init__(
        self,
        source: Source,
        http_client: httpx.AsyncClient | None = None,
        *,
        proxy_br_url: str | None = None,
        proxy_br_token: str | None = None,
    ) -> None:
        self.source = source
        self._client = http_client
        self._owns_client = http_client is None
        self._proxy_br_url = proxy_br_url
        self._proxy_br_token = proxy_br_token

    async def __aenter__(self) -> Self:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(limits.HTTP_TIMEOUT_SECONDS),
                headers={"User-Agent": USER_AGENT, "Accept": DEFAULT_ACCEPT},
                follow_redirects=True,
                max_redirects=5,
            )
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def name(self) -> str:
        """Identificador da fonte para logs."""
        return self.source.id

    @abstractmethod
    async def collect(self) -> list[RawItem]:
        """Coleta itens da fonte.

        Implementações devem ser **isoladas**: falhas aqui não podem
        derrubar o pipeline (orquestrador faz try/except por fonte).
        """

    async def fetch(self, url: str | None = None) -> str:
        """Fetch URL com validação anti-SSRF, rate limit e retry.

        Para fontes `geo_restricted=True`, em ConnectTimeout/ConnectError,
        RemoteProtocolError (servidor envia headers HTTP malformados) ou
        HTTP 403/451 (geo-block típico), faz fallback automático via Cloud
        Function proxy (PROXY_BR_URL).
        """
        target = url or self.source.url
        validate_url(target)  # anti-SSRF; pode levantar UnsafeURLError

        if self._client is None:
            msg = "BaseCollector deve ser usado com `async with` ou http_client explícito"
            raise CollectorError(msg)

        domain = _domain_of(target)
        await _DomainRateLimiter.acquire(domain, limits.DOMAIN_REQUESTS_INTERVAL_SECONDS)

        try:
            return await self._fetch_direct(target)
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            # RemoteProtocolError: servidor envia headers HTTP malformados
            # (ex: múltiplos Transfer-Encoding) que h11 rejeita por RFC 7230.
            # TJRJ exibe esse comportamento em GH Actions runner US (não local BR).
            # proxy_br normaliza headers e contorna o problema.
            return await self._maybe_fallback_proxy(target, type(e).__name__, exc=e)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in GEO_BLOCK_STATUS:
                return await self._maybe_fallback_proxy(
                    target, f"HTTP{e.response.status_code}", exc=e
                )
            raise

    async def _maybe_fallback_proxy(self, target: str, reason: str, *, exc: BaseException) -> str:
        """Tenta proxy_br se source é geo_restricted; senão re-raise original."""
        if not self.source.geo_restricted or not self._proxy_br_url:
            raise exc
        logger.info(
            "fetch.fallback_via_proxy",
            source=self.source.id,
            target=target,
            reason=reason,
        )
        return await self._fetch_via_proxy(target)

    async def _fetch_direct(self, target: str) -> str:
        """Fetch direto com retry exponencial.

        429/503 NÃO entram no retry — esses status indicam que o servidor
        precisa de janela maior que 30s para se recuperar; melhor falhar
        imediatamente e tentar na próxima execução do cron.
        """
        if self._client is None:  # pragma: no cover - defensive, __aenter__ garante
            msg = "client não inicializado"
            raise CollectorError(msg)
        client = self._client

        def _should_retry(exc: BaseException) -> bool:
            # 429/503: rate-limit / overload — backoff de 30s não resolve.
            if isinstance(exc, httpx.HTTPStatusError) and (
                exc.response.status_code in NO_RETRY_STATUS
            ):
                return False
            return isinstance(exc, (httpx.HTTPError, asyncio.TimeoutError))

        retryer = AsyncRetrying(
            stop=stop_after_attempt(limits.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(multiplier=1, min=2, max=20),
            retry=retry_if_exception(_should_retry),
            reraise=True,
        )
        try:
            async for attempt in retryer:
                with attempt:
                    response = await client.get(target)
                    response.raise_for_status()
                    return response.text
        except httpx.HTTPStatusError as e:
            if e.response.status_code in NO_RETRY_STATUS:
                msg = f"rate-limited ({e.response.status_code}) em {target}"
                raise RateLimitedError(msg) from e
            raise
        msg = f"Fetch falhou após retries: {target}"  # pragma: no cover
        raise CollectorError(msg)  # pragma: no cover

    async def _fetch_via_proxy(self, target: str) -> str:
        """Fetch através do Cloud Function proxy_br (sem retry — proxy já é o retry)."""
        if self._client is None:  # pragma: no cover - defensive
            msg = "client não inicializado"
            raise CollectorError(msg)
        if not self._proxy_br_url or not self._proxy_br_token:  # pragma: no cover - guarded acima
            msg = "proxy não configurado mas chamado"
            raise CollectorError(msg)

        # urllib quote em vez de httpx.QueryParams — mais robusto para URLs longas
        from urllib.parse import quote  # noqa: PLC0415

        proxy_url = f"{self._proxy_br_url.rstrip('/')}?url={quote(target, safe='')}"
        try:
            response = await self._client.get(
                proxy_url,
                headers={"X-Proxy-Token": self._proxy_br_token},
                timeout=httpx.Timeout(limits.HTTP_TIMEOUT_SECONDS * 2),
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            msg = f"proxy fetch falhou: {type(e).__name__}"
            raise CollectorError(msg) from e

        # response.content + decode explícito é mais robusto que response.text:
        # alguns proxies retornam Content-Type sem charset, o que faz httpx
        # cair em 'ascii' decode e silenciosamente perder bytes não-ASCII.
        body_bytes = response.content
        logger.info(
            "fetch.proxy_response",
            source=self.source.id,
            bytes=len(body_bytes),
            content_type=response.headers.get("content-type", "")[:50],
        )
        return body_bytes.decode("utf-8", errors="replace")

        # Inalcançável (reraise=True acima sempre relança em última falha).
        msg = f"Fetch falhou após retries: {target}"  # pragma: no cover
        raise CollectorError(msg)  # pragma: no cover

    def make_raw_item(
        self,
        titulo: str,
        url: str,
        texto: str | None = None,
        data_pub: datetime | None = None,
        content_for_hash: str | None = None,
        sanitize: bool = True,
    ) -> RawItem:
        """Helper para construir RawItem com hash automático.

        Args:
            sanitize: V7 (Pentest) — aplica `sanitize_html` em `texto`
                antes de criar RawItem. Defesa adicional além do
                Jinja2 autoescape nos templates. Default True.

        `content_for_hash` permite estabilidade entre runs: se passado,
        determinístico; senão, usa fallback `source_id|url|titulo`.
        """
        from monitoritcd.core.sanitize import sanitize_html  # noqa: PLC0415

        hash_input = content_for_hash if content_for_hash else f"{self.source.id}|{url}|{titulo}"
        # V7 (Pentest): sanitiza HTML em texto_raw antes de armazenar.
        # `<script>`, event handlers, etc. removidos; defesa contra XSS
        # storage caso template futuro use {{ texto_raw|safe }}.
        texto_safe = sanitize_html(texto) if (sanitize and texto and "<" in texto) else texto
        return RawItem(
            source_id=self.source.id,
            titulo_raw=titulo,
            url=url,
            texto_raw=texto_safe,
            data_publicacao=data_pub,
            fetched_at=datetime.now(UTC),
            content_hash=content_hash(hash_input),
        )
