"""Notificação por e-mail via SMTP Gmail.

Uso:
    notifier = EmailNotifier(settings)
    await notifier.send_digest(documentos, digest_label="Diário")

Princípios canônicos aplicados:
1. **Jinja2 com `autoescape=True`** — XSS em conteúdo de itens neutralizado.
2. **CSP no `<head>`** — restringe execução mesmo se template fosse comprometido.
3. **`SecretStr` para senha** — nunca em logs ou exceções.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import TYPE_CHECKING

import structlog
from jinja2 import Environment, PackageLoader, select_autoescape

from monitoritcd.notifiers.severity import emoji_for_tier, label_for_tier

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from monitoritcd.core.config import Settings
    from monitoritcd.core.models import Documento

logger = structlog.get_logger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Cores por tier (CSS inline em template HTML)
TIER_COLORS: dict[str, str] = {
    "critico": "#d32f2f",
    "alta": "#f57c00",
    "normal": "#1976d2",
    "baixa": "#388e3c",
    "descartado": "#9e9e9e",
}

TIPO_LABELS: dict[str, str] = {
    "projeto_lei": "Projeto de Lei",
    "lei_sancionada": "Lei sancionada",
    "decreto": "Decreto",
    "instrucao_normativa": "Instrução Normativa",
    "portaria": "Portaria",
    "noticia": "Notícia",
    "jurisprudencia": "Jurisprudência",
    "doutrina": "Doutrina",
    "outro": "Outro",
}


def build_jinja_env() -> Environment:
    """Constrói Jinja2 com autoescape obrigatório (anti-XSS)."""
    return Environment(
        loader=PackageLoader("monitoritcd.notifiers", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _render_item_context(doc: Documento) -> dict[str, str]:
    """Constrói o contexto Jinja2 para um único item.

    Importante: NÃO modifica `original` — apenas extrai dados para template.
    """
    tier_value = doc.llm.severity_tier.value if doc.llm else "normal"
    tipo_value = doc.llm.tipo.value if doc.llm else "outro"
    return {
        "titulo": doc.original.titulo_raw,
        "url": doc.original.url,
        "resumo": doc.llm.resumo if doc.llm else "",
        "uf": doc.source.uf,
        "tipo_label": TIPO_LABELS.get(tipo_value, tipo_value),
        "tier_emoji": emoji_for_tier(doc.llm.severity_tier) if doc.llm else "⚪",
        "tier_label": label_for_tier(doc.llm.severity_tier) if doc.llm else "—",
        "tier_color": TIER_COLORS.get(tier_value, "#666"),
        "data_pub": doc.original.data_publicacao.strftime("%d/%m/%Y")
        if doc.original.data_publicacao
        else "",
        "fonte_nome": doc.source.nome,
    }


def render_email(
    docs: Sequence[Documento],
    *,
    digest_label: str,
    data_geracao: datetime,
    subject: str | None = None,
    env: Environment | None = None,
) -> tuple[str, str]:
    """Renderiza assunto + corpo HTML.

    Returns:
        (subject, body_html)
    """
    env = env or build_jinja_env()
    items = [_render_item_context(d) for d in docs]
    highlights = [it for it in items if it["tier_emoji"] in ("🔴", "🟠")][:3]

    final_subject = subject or f"[MonitorITCD] {digest_label} — {len(docs)} novidades"

    template = env.get_template("email.html.j2")
    body = template.render(
        items=items,
        highlights=highlights,
        digest_label=digest_label,
        data_geracao=data_geracao.strftime("%d/%m/%Y %H:%M"),
        subject=final_subject,
    )
    return final_subject, body


def _send_via_smtp_sync(
    *,
    sender: str,
    password: str,
    recipient: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> None:
    """Envia via SMTP TLS — bloqueante; chamar via `asyncio.to_thread`."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    if body_text:
        msg.set_content(body_text)
    else:
        msg.set_content("Seu cliente de e-mail não suporta HTML.")
    msg.add_alternative(body_html, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(sender, password)
        smtp.send_message(msg)


class EmailNotifier:
    """Notificador por e-mail via Gmail SMTP."""

    def __init__(self, settings: Settings, env: Environment | None = None) -> None:
        self._settings = settings
        self._env = env or build_jinja_env()

    async def send_digest(
        self,
        docs: Sequence[Documento],
        *,
        digest_label: str,
        data_geracao: datetime,
    ) -> None:
        """Envia digest com lista de docs."""
        subject, body = render_email(
            docs,
            digest_label=digest_label,
            data_geracao=data_geracao,
            env=self._env,
        )

        await asyncio.to_thread(
            _send_via_smtp_sync,
            sender=self._settings.GMAIL_USER,
            password=self._settings.GMAIL_APP_PASSWORD.get_secret_value(),
            recipient=self._settings.OWNER_EMAIL,
            subject=subject,
            body_html=body,
        )

        logger.info(
            "email.sent",
            recipient=self._settings.OWNER_EMAIL,
            count=len(docs),
            digest=digest_label,
        )
