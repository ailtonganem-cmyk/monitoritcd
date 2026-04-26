"""Notificadores multi-canal alternativos a Email + Telegram.

Cobre IDEAS.md Categoria 5 (#146-#170) — canais opcionais para o dono
configurar conforme preferência. Todos via webhook/POST simples (zero
dependência de bibliotecas externas além de httpx já existente).

Canais implementados:
- DiscordNotifier (#146) — webhook
- NtfyNotifier (#147, #165) — push grátis
- PushoverNotifier (#148) — push pessoal
- SlackNotifier (#149) — webhook
- MatrixNotifier (#152) — Matrix Synapse
- GenericWebhookNotifier (#161) — POST JSON arbitrário

Princípios canônicos aplicados:
- Princípio 1 (input não confiável): URL do webhook validada via validate_url
- Princípio 2: timeout 30s em todas as chamadas; payloads truncados
- Princípio 3: tokens via SecretStr (passados pela classe; nunca hardcoded)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitoritcd.core import limits
from monitoritcd.security.url_validator import validate_url

if TYPE_CHECKING:
    from monitoritcd.core.models import Documento

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(30.0)
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


class ChannelNotifier(Protocol):
    """Interface comum para notificadores adicionais."""

    async def notify(self, title: str, message: str, *, url: str | None = None) -> None: ...


def _retryer() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(limits.RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )


class DiscordNotifier:
    """#146 — Discord via webhook (sem auth, URL é o segredo)."""

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        validate_url(webhook_url)
        self._url = webhook_url
        self._client = client

    async def notify(self, title: str, message: str, *, url: str | None = None) -> None:
        payload = {
            "embeds": [
                {
                    "title": title[:256],
                    "description": message[:4000],
                    "url": url,
                    "color": 0x1976D2,
                }
            ]
        }
        client = self._client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        async for attempt in _retryer():
            with attempt:
                resp = await client.post(self._url, json=payload, timeout=DEFAULT_TIMEOUT)
                resp.raise_for_status()
        if self._client is None:
            await client.aclose()
        logger.info("discord.sent", title_len=len(title))


class NtfyNotifier:
    """#147, #165 — ntfy.sh push grátis (HTTP simples; topic é o "secret")."""

    def __init__(self, topic_url: str, client: httpx.AsyncClient | None = None) -> None:
        validate_url(topic_url)
        self._url = topic_url
        self._client = client

    async def notify(self, title: str, message: str, *, url: str | None = None) -> None:
        # ntfy headers exigem ASCII; títulos UTF-8 vão como :encoded RFC 2047
        # ou simplificamos via ASCII-safe (substituindo não-ASCII por ?).
        ascii_title = title[:200].encode("ascii", errors="replace").decode("ascii")
        headers = {"Title": ascii_title, "Tags": "page_facing_up"}
        if url:
            headers["Click"] = url
        client = self._client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        async for attempt in _retryer():
            with attempt:
                resp = await client.post(
                    self._url,
                    content=message[:4000].encode("utf-8"),
                    headers=headers,
                    timeout=DEFAULT_TIMEOUT,
                )
                resp.raise_for_status()
        if self._client is None:
            await client.aclose()
        logger.info("ntfy.sent")


class PushoverNotifier:
    """#148 — Pushover (token + user_key)."""

    def __init__(
        self,
        token: str,
        user_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token or not user_key:
            msg = "Pushover requer token e user_key"
            raise ValueError(msg)
        self._token = token
        self._user = user_key
        self._client = client

    async def notify(self, title: str, message: str, *, url: str | None = None) -> None:
        data = {
            "token": self._token,
            "user": self._user,
            "title": title[:250],
            "message": message[:1024],
        }
        if url:
            data["url"] = url
        client = self._client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        async for attempt in _retryer():
            with attempt:
                resp = await client.post(PUSHOVER_URL, data=data, timeout=DEFAULT_TIMEOUT)
                resp.raise_for_status()
        if self._client is None:
            await client.aclose()
        logger.info("pushover.sent")


class SlackNotifier:
    """#149 — Slack via webhook (URL é o secret)."""

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        validate_url(webhook_url)
        self._url = webhook_url
        self._client = client

    async def notify(self, title: str, message: str, *, url: str | None = None) -> None:
        title_text = f"<{url}|{title}>" if url else title
        payload = {
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title_text}*"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": message[:3000]}},
            ]
        }
        client = self._client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        async for attempt in _retryer():
            with attempt:
                resp = await client.post(self._url, json=payload, timeout=DEFAULT_TIMEOUT)
                resp.raise_for_status()
        if self._client is None:
            await client.aclose()
        logger.info("slack.sent")


class MatrixNotifier:
    """#152 — Matrix.org / Synapse (room_id + access_token)."""

    def __init__(
        self,
        homeserver_url: str,
        room_id: str,
        access_token: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        validate_url(homeserver_url)
        if not access_token or not room_id:
            msg = "Matrix requer room_id e access_token"
            raise ValueError(msg)
        self._homeserver = homeserver_url.rstrip("/")
        self._room_id = room_id
        self._token = access_token
        self._client = client

    async def notify(self, title: str, message: str, *, url: str | None = None) -> None:
        body = f"**{title}**\n\n{message}"
        if url:
            body += f"\n\n{url}"
        # Matrix usa PUT com txn_id; aqui geramos um simples baseado no hash
        txn = abs(hash((title, message))) % (10**12)
        send_url = (
            f"{self._homeserver}/_matrix/client/v3/rooms/{self._room_id}/send/m.room.message/{txn}"
        )
        payload = {"msgtype": "m.text", "body": body[:4000], "format": "org.matrix.custom.html"}
        client = self._client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        async for attempt in _retryer():
            with attempt:
                resp = await client.put(
                    send_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=DEFAULT_TIMEOUT,
                )
                resp.raise_for_status()
        if self._client is None:
            await client.aclose()
        logger.info("matrix.sent")


class GenericWebhookNotifier:
    """#161 — POST JSON arbitrário para URL configurável."""

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        validate_url(webhook_url)
        self._url = webhook_url
        self._client = client

    async def notify(self, title: str, message: str, *, url: str | None = None) -> None:
        payload = {
            "title": title,
            "message": message,
            "url": url,
            "source": "monitoritcd",
        }
        client = self._client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        async for attempt in _retryer():
            with attempt:
                resp = await client.post(self._url, json=payload, timeout=DEFAULT_TIMEOUT)
                resp.raise_for_status()
        if self._client is None:
            await client.aclose()
        logger.info("webhook.sent")


async def broadcast(
    notifiers: list[ChannelNotifier],
    *,
    title: str,
    message: str,
    url: str | None = None,
) -> dict[str, bool]:
    """Envia para todos os canais; retorna dict por nome → True/False.

    Falha em um canal NÃO derruba os demais (Princípio: defense-in-depth).
    """
    results: dict[str, bool] = {}
    for n in notifiers:
        name = type(n).__name__
        try:
            await n.notify(title, message, url=url)
            results[name] = True
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("broadcast.failed", channel=name, error=str(e))
            results[name] = False
    return results


def doc_to_notification(doc: Documento) -> tuple[str, str, str | None]:
    """Helper: converte Documento em (title, message, url) para canais."""
    title = doc.original.titulo_raw[:200]
    parts: list[str] = []
    if doc.llm:
        parts.append(f"[{doc.llm.severity_tier.value.upper()}] {doc.source.uf}")
        parts.append(doc.llm.resumo)
    else:
        parts.append(f"[{doc.source.uf}]")
    return title, "\n".join(parts), doc.original.url


__all__ = [
    "ChannelNotifier",
    "DiscordNotifier",
    "GenericWebhookNotifier",
    "MatrixNotifier",
    "NtfyNotifier",
    "PushoverNotifier",
    "SlackNotifier",
    "broadcast",
    "doc_to_notification",
]
