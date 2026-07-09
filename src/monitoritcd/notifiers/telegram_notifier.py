"""Notificação via Telegram Bot API.

Envia mensagens em MarkdownV2 (com escape correto) ao chat do dono.
Faz split automático se mensagem ultrapassa 4096 chars.

Cobre IDEAS.md Categoria 4 — Notificação por Telegram.

Princípios canônicos aplicados:
1. **Escape MarkdownV2** sempre antes do envio (#124).
2. **MAX_TELEGRAM_MSG_BYTES** enforcement via `split_for_telegram` (#136).
3. **Bot token via `SecretStr`** — nunca em logs.
4. **Destinatário** via env var: owner (`TELEGRAM_OWNER_CHAT_ID`) por default;
   o digest de novidades pode ir a um grupo (`TELEGRAM_GROUP_CHAT_ID`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from monitoritcd.core import limits
from monitoritcd.notifiers.email_notifier import (
    TIPO_LABELS,
    _render_item_context,
    build_jinja_env,
)
from monitoritcd.notifiers.telegram_actions import (
    InlineKeyboard,
    build_item_keyboard,
)
from monitoritcd.security.markdown_escape import (
    escape_markdown_v2,
    split_for_telegram,
    strip_markdown_v2_escapes,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from jinja2 import Environment

    from monitoritcd.core.config import Settings
    from monitoritcd.core.models import Documento

logger = structlog.get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"

# #131 — DND noturno automático (22h-7h BRT por default)
DND_INICIO_BRT: Final[int] = 22
DND_FIM_BRT: Final[int] = 7
BRT_OFFSET_HOURS: Final[int] = 3  # UTC -3 = BRT


def is_dnd_window(now: datetime, *, inicio: int = DND_INICIO_BRT, fim: int = DND_FIM_BRT) -> bool:
    """#131 — True se `now` cai na janela DND noturna (BRT)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    hour_brt = (now.hour - BRT_OFFSET_HOURS) % 24
    if inicio < fim:
        return inicio <= hour_brt < fim
    # Janela cruza meia-noite (ex: 22-7)
    return hour_brt >= inicio or hour_brt < fim


def _is_retryable_status(status_code: int) -> bool:
    """429 (rate limit) e 5xx são transitórios.

    Demais 4xx (ex: 400 "can't parse entities") são permanentes: repetir a
    mesma requisição nunca muda o resultado, só desperdiça tentativas e
    esconde o motivo real do erro atrás de um retry inútil.
    """
    return status_code == httpx.codes.TOO_MANY_REQUESTS or httpx.codes.is_server_error(status_code)


def _extract_error_description(response: httpx.Response) -> str:
    """Extrai `description` do erro da API do Telegram.

    Faz fallback para o corpo cru (`response.text`) se a resposta não for
    o JSON `{"ok": false, "description": "..."}` esperado.
    """
    try:
        return str(response.json()["description"])
    except (ValueError, KeyError, TypeError):
        return response.text


def _escape_for_template(value: str) -> str:
    """Filter Jinja2 que escapa para MarkdownV2."""
    return escape_markdown_v2(value)


def _escape_items(docs: Sequence[Documento]) -> list[dict[str, str]]:
    """Escapa items para MarkdownV2 (compartilhado entre modos)."""
    items: list[dict[str, str]] = []
    for d in docs:
        ctx = _render_item_context(d)
        escaped: dict[str, str] = {
            k: escape_markdown_v2(v) if isinstance(v, str) and k != "url" else v
            for k, v in ctx.items()
        }
        # URL não escapa, mas neutraliza `)` e `\\` para não quebrar Markdown
        escaped["url"] = ctx["url"].replace("\\", "\\\\").replace(")", "\\)")
        items.append(escaped)
    return items


def render_telegram(
    docs: Sequence[Documento],
    *,
    digest_label: str,
    data_geracao: datetime,
    env: Environment | None = None,
    group_by: str | None = None,
) -> str:
    """Renderiza mensagem MarkdownV2 com escape correto.

    Args:
        docs: documentos.
        digest_label: rótulo do digest.
        data_geracao: timestamp.
        env: Jinja2 env.
        group_by: None (default), "uf" (#127), ou "tipo" (#128).
    """
    env = env or build_jinja_env()
    items = _escape_items(docs)

    if group_by in ("uf", "tipo"):
        return _render_grouped(items, digest_label, data_geracao, group_by)

    template = env.get_template("telegram.md.j2")
    return template.render(
        items=items,
        digest_label=escape_markdown_v2(digest_label),
        data_geracao=escape_markdown_v2(data_geracao.strftime("%d/%m/%Y %H:%M")),
    )


def _render_grouped(
    items: list[dict[str, str]],
    digest_label: str,
    data_geracao: datetime,
    group_by: str,
) -> str:
    """#127, #128 — agrupa itens por UF ou tipo."""
    groups: dict[str, list[dict[str, str]]] = {}
    for item in items:
        key = item.get("uf", "_outro") if group_by == "uf" else item.get("tipo_label", "Outro")
        groups.setdefault(key, []).append(item)

    n = len(items)
    unidade = "novidade" if n == 1 else "novidades"
    header = (
        f"*📊 MonitorITCD — {escape_markdown_v2(digest_label)}*\n"
        f"_{escape_markdown_v2(data_geracao.strftime('%d/%m/%Y %H:%M'))} · "
        f"{n} {unidade}_\n"
    )
    parts = [header]
    for grupo, gitens in sorted(groups.items()):
        parts.append(f"\n*{escape_markdown_v2(grupo)}* \\({len(gitens)}\\)")
        parts.extend(
            f"{item['tier_emoji']} *{item['titulo']}*\n"
            f"{item['tipo_label']}{' · ' + item['data_pub'] if item.get('data_pub') else ''}\n"
            f"{item['resumo']}\n"
            f"[Abrir original]({item['url']})"
            for item in gitens
        )
    return "\n".join(parts)


def render_quote(text: str) -> str:
    """#141 — formata texto como quote MarkdownV2 (`>` no início de cada linha)."""
    lines = text.splitlines() or [text]
    return "\n".join(f">{escape_markdown_v2(ln)}" for ln in lines)


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

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            msg = "TelegramNotifier deve ser usado com `async with`"
            raise RuntimeError(msg)
        return self._client

    def _api_url(self, method: str) -> str:
        token = self._settings.TELEGRAM_BOT_TOKEN.get_secret_value()
        return f"{TELEGRAM_API_BASE}/bot{token}/{method}"

    def _retryer(self) -> AsyncRetrying:
        def _should_retry(exc: BaseException) -> bool:
            if isinstance(exc, httpx.HTTPStatusError):
                return _is_retryable_status(exc.response.status_code)
            return isinstance(exc, httpx.HTTPError)

        return AsyncRetrying(
            stop=stop_after_attempt(limits.RETRY_MAX_ATTEMPTS),
            wait=wait_exponential(multiplier=1, min=2, max=20),
            retry=retry_if_exception(_should_retry),
            reraise=True,
        )

    async def _post_chunk(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, object],
        *,
        chat_id: int,
    ) -> httpx.Response:
        """POST de 1 payload à API do Telegram.

        Retry (via `_retryer`) cobre só falha de transporte e 429/5xx —
        transitórios. 4xx permanente (ex: 400 "can't parse entities") não é
        retentado: loga o corpo do erro e devolve a resposta sem levantar —
        quem chama decide o que fazer (`send_message` reenvia em
        plain-text só para 400).
        """
        response: httpx.Response | None = None
        async for attempt in self._retryer():
            with attempt:
                response = await client.post(url, json=payload)
                if httpx.codes.is_error(response.status_code):
                    logger.warning(
                        "telegram.api_error",
                        status=response.status_code,
                        description=_extract_error_description(response),
                        chat_id=chat_id,
                    )
                if _is_retryable_status(response.status_code):
                    response.raise_for_status()
        if response is None:  # pragma: no cover - retryer sempre atribui response ou relança
            msg = "resposta ausente após POST ao Telegram"
            raise RuntimeError(msg)
        return response

    async def send_message(
        self,
        text: str,
        *,
        keyboard: InlineKeyboard | None = None,
        reply_to_message_id: int | None = None,
        chat_id: int | None = None,
    ) -> int | None:
        """Envia uma mensagem (split em chunks ≤ 4096 bytes).

        Args:
            text: texto MarkdownV2.
            keyboard: inline_keyboard opcional (#121, #133, #134, #135, #140).
            reply_to_message_id: threading (#137).
            chat_id: destino explícito (ex: grupo); default = TELEGRAM_OWNER_CHAT_ID.

        Returns:
            message_id da última mensagem enviada (para edit/pin posterior),
            ou None se split em múltiplos chunks impede ID único.

        Note:
            Chunk que falha com 400 (MarkdownV2 inválido — "can't parse
            entities") é reenviado UMA vez em texto plano (sem `parse_mode`)
            para garantir a entrega mesmo com formatação quebrada.
        """
        client = self._ensure_client()
        url = self._api_url("sendMessage")
        chat_id = chat_id if chat_id is not None else self._settings.TELEGRAM_OWNER_CHAT_ID
        chunks = split_for_telegram(text, max_bytes=limits.MAX_TELEGRAM_MSG_BYTES)

        last_message_id: int | None = None
        for i, chunk in enumerate(chunks):
            payload: dict[str, object] = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            }
            # keyboard e reply só na PRIMEIRA mensagem do split (lê melhor)
            if i == 0 and keyboard is not None:
                payload["reply_markup"] = {"inline_keyboard": keyboard}
            if i == 0 and reply_to_message_id is not None:
                payload["reply_parameters"] = {"message_id": reply_to_message_id}

            response = await self._post_chunk(client, url, payload, chat_id=chat_id)
            if response.status_code == httpx.codes.BAD_REQUEST:
                # MarkdownV2 inválido é permanente — retry não ajuda.
                # Reenvia o MESMO chunk em texto plano, 1x só.
                fallback_payload = dict(payload)
                fallback_payload["text"] = strip_markdown_v2_escapes(chunk)
                fallback_payload.pop("parse_mode", None)
                response = await self._post_chunk(client, url, fallback_payload, chat_id=chat_id)
            response.raise_for_status()
            body = response.json()
            last_message_id = body.get("result", {}).get("message_id")

        logger.info("telegram.sent", chat_id=chat_id, chunks=len(chunks))
        return last_message_id if len(chunks) == 1 else None

    async def pin_message(self, message_id: int, *, disable_notification: bool = True) -> None:
        """#122 — Pin de mensagem (ex: alerta crítico)."""
        client = self._ensure_client()
        async for attempt in self._retryer():
            with attempt:
                response = await client.post(
                    self._api_url("pinChatMessage"),
                    json={
                        "chat_id": self._settings.TELEGRAM_OWNER_CHAT_ID,
                        "message_id": message_id,
                        "disable_notification": disable_notification,
                    },
                )
                response.raise_for_status()
        logger.info("telegram.pinned", message_id=message_id)

    async def unpin_message(self, message_id: int) -> None:
        """Despin de mensagem específica."""
        client = self._ensure_client()
        async for attempt in self._retryer():
            with attempt:
                response = await client.post(
                    self._api_url("unpinChatMessage"),
                    json={
                        "chat_id": self._settings.TELEGRAM_OWNER_CHAT_ID,
                        "message_id": message_id,
                    },
                )
                response.raise_for_status()

    async def edit_message_text(
        self,
        message_id: int,
        text: str,
        *,
        keyboard: InlineKeyboard | None = None,
    ) -> None:
        """#132 — Edita mensagem in-place (ex: ao chegar correlato)."""
        client = self._ensure_client()
        payload: dict[str, object] = {
            "chat_id": self._settings.TELEGRAM_OWNER_CHAT_ID,
            "message_id": message_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        async for attempt in self._retryer():
            with attempt:
                response = await client.post(self._api_url("editMessageText"), json=payload)
                response.raise_for_status()

    async def send_chat_action(self, action: str = "typing") -> None:
        """#138 — Status "digitando…" durante operações longas.

        Args:
            action: "typing", "upload_document", etc.
        """
        client = self._ensure_client()
        # chat_action é fire-and-forget; sem retry agressivo
        try:
            await client.post(
                self._api_url("sendChatAction"),
                json={"chat_id": self._settings.TELEGRAM_OWNER_CHAT_ID, "action": action},
                timeout=httpx.Timeout(5.0),
            )
        except httpx.HTTPError:
            # Não bloqueia em caso de falha — apenas indicação visual
            logger.debug("telegram.chat_action_failed", action=action)

    async def send_digest(
        self,
        docs: Sequence[Documento],
        *,
        digest_label: str,
        data_geracao: datetime,
        group_by: str | None = None,
        with_keyboards: bool = False,
        respect_dnd: bool = False,
        chat_id: int | None = None,
    ) -> int | None:
        """Renderiza e envia digest via Telegram.

        Args:
            docs: documentos.
            digest_label: rótulo.
            data_geracao: timestamp.
            group_by: "uf" (#127), "tipo" (#128), ou None.
            with_keyboards: se True E há 1 doc, anexa inline keyboard (#121).
            respect_dnd: se True, retorna sem enviar quando em janela DND (#131).
            chat_id: destino explícito (ex: grupo); default = TELEGRAM_OWNER_CHAT_ID.
        """
        if respect_dnd and is_dnd_window(data_geracao):
            logger.info(
                "telegram.dnd_skip",
                hour_brt=(data_geracao.hour - BRT_OFFSET_HOURS) % 24,
            )
            return None

        text = render_telegram(
            docs,
            digest_label=digest_label,
            data_geracao=data_geracao,
            env=self._env,
            group_by=group_by,
        )
        keyboard: InlineKeyboard | None = None
        if with_keyboards and len(docs) == 1:
            doc = docs[0]
            keyboard = build_item_keyboard(
                doc.doc_id,
                url=doc.original.url,
            )
        return await self.send_message(text, keyboard=keyboard, chat_id=chat_id)


# Re-export de TIPO_LABELS para evitar import circular nas rotas externas
__all__ = [
    "BRT_OFFSET_HOURS",
    "DND_FIM_BRT",
    "DND_INICIO_BRT",
    "TIPO_LABELS",
    "TelegramNotifier",
    "is_dnd_window",
    "render_quote",
    "render_telegram",
]
