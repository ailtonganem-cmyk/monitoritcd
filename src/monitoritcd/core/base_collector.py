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
    retry_if_exception_type,
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

logger = structlog.get_logger(__name__)


class CollectorError(Exception):
    """Erro durante coleta. Captura no orquestrador para isolar fontes."""


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
    ) -> None:
        self.source = source
        self._client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> Self:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(limits.HTTP_TIMEOUT_SECONDS),
                headers={"User-Agent": USER_AGENT},
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
        """Fetch URL com validação anti-SSRF, rate limit e retry."""
        target = url or self.source.url
        validate_url(target)  # anti-SSRF; pode levantar UnsafeURLError

        if self._client is None:
            msg = "BaseCollector deve ser usado com `async with` ou http_client explícito"
            raise CollectorError(msg)

        domain = _domain_of(target)
        await _DomainRateLimiter.acquire(domain, limits.DOMAIN_REQUESTS_INTERVAL_SECONDS)

        retryer = AsyncRetrying(
            stop=stop_after_attempt(limits.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(multiplier=1, min=2, max=20),
            retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
            reraise=True,
        )

        async for attempt in retryer:
            with attempt:
                response = await self._client.get(target)
                response.raise_for_status()
                return response.text

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
    ) -> RawItem:
        """Helper para construir RawItem com hash automático.

        `content_for_hash` permite estabilidade entre runs: se passado,
        determinístico; senão, usa fallback `source_id|url|titulo`.
        """
        hash_input = content_for_hash if content_for_hash else f"{self.source.id}|{url}|{titulo}"
        return RawItem(
            source_id=self.source.id,
            titulo_raw=titulo,
            url=url,
            texto_raw=texto,
            data_publicacao=data_pub,
            fetched_at=datetime.now(UTC),
            content_hash=content_hash(hash_input),
        )
