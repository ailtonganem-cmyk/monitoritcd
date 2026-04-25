"""Notificação via Telegram Bot API.

Envia mensagens em MarkdownV2 (com escape correto) ao chat do dono.
Faz split automático se mensagem ultrapassa 4096 chars.

Princípios canônicos aplicados:
1. **Escape MarkdownV2** sempre antes do envio.
2. **MAX_TELEGRAM_MSG_BYTES** enforcement via `split_for_telegram`.
3. **Bot token via `SecretStr`** — nunca em logs.
4. **Identidade do destinatário** via env var (`TELEGRAM_OWNER_CHAT_ID`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitoritcd.core import limits
from monitoritcd.notifiers.email_notifier import (
    TIPO_LABELS,
    _render_item_context,
    build_jinja_env,
)
from monitoritcd.security.markdown_escape import (
    escape_markdown_v2,
    split_for_telegram,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from jinja2 import Environment

    from monitoritcd.core.config import Settings
    from monitoritcd.core.models import Documento

logger = structlog.get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


def _escape_for_template(value: str) -> str:
    """Filter Jinja2 que escapa para MarkdownV2."""
    return escape_markdown_v2(value)


def render_telegram(
    docs: Sequence[Documento],
    *,
    digest_label: str,
    data_geracao: datetime,
    env: Environment | None = None,
) -> str:
    """Renderiza mensagem MarkdownV2 com escape correto.

    Os campos textuais (titulo, resumo, etc.) são **escapados** antes do template.
    """
    env = env or build_jinja_env()

    items = []
    for d in docs:
        ctx = _render_item_context(d)
        # Escapa todos os campos textuais que vão para o Markdown
        escaped: dict[str, str] = {
            k: escape_markdown_v2(v) if isinstance(v, str) and k != "url" else v
            for k, v in ctx.items()
        }
        # URL não pode ser escapada (vai dentro de [text](url))
        # mas precisa escapar `)` e `\\`
        escaped["url"] = ctx["url"].replace("\\", "\\\\").replace(")", "\\)")
        items.append(escaped)

    template = env.get_template("telegram.md.j2")
    return template.render(
        items=items,
        digest_label=escape_markdown_v2(digest_label),
        data_geracao=escape_markdown_v2(data_geracao.strftime("%d/%m/%Y %H:%M")),
    )


class TelegramNotifier:
    """Notificador via Telegram Bot API."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        env: Environment | None = None,
    ) -> None:
        self._settings = settings
        self._client = http_client
        self._owns_client = http_client is None
        self._env = env or build_jinja_env()

    async def __aenter__(self) -> TelegramNotifier:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send_message(self, text: str) -> None:
        """Envia uma mensagem (split em chunks ≤ 4096 bytes)."""
        if self._client is None:
            msg = "TelegramNotifier deve ser usado com `async with`"
            raise RuntimeError(msg)

        token = self._settings.TELEGRAM_BOT_TOKEN.get_secret_value()
        url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
        chat_id = self._settings.TELEGRAM_OWNER_CHAT_ID

        chunks = split_for_telegram(text, max_bytes=limits.MAX_TELEGRAM_MSG_BYTES)

        retryer = AsyncRetrying(
            stop=stop_after_attempt(limits.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(multiplier=1, min=2, max=20),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True,
        )

        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            }
            async for attempt in retryer:
                with attempt:
                    response = await self._client.post(url, json=payload)
                    response.raise_for_status()

        logger.info("telegram.sent", chat_id=chat_id, chunks=len(chunks))

    async def send_digest(
        self,
        docs: Sequence[Documento],
        *,
        digest_label: str,
        data_geracao: datetime,
    ) -> None:
        """Renderiza e envia digest via Telegram."""
        text = render_telegram(
            docs,
            digest_label=digest_label,
            data_geracao=data_geracao,
            env=self._env,
        )
        await self.send_message(text)


# Re-export de TIPO_LABELS para evitar import circular nas rotas externas
__all__ = ["TIPO_LABELS", "TelegramNotifier", "render_telegram"]
