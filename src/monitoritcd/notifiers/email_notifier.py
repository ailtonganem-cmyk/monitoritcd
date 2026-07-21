"""Notificação por e-mail via API do Resend.

Suporta múltiplos templates (default/compacto/executivo/newsletter — #111-#114),
saudação dinâmica por horário (#117), subject configurável com placeholders
(#110), anexos CSV/JSON (#106, #107), reply-to configurável (#120), e
dark-mode automático (#97) via prefers-color-scheme nos templates.

Princípios canônicos aplicados:
1. **Jinja2 com `autoescape=True`** — XSS em conteúdo de itens neutralizado.
2. **CSP no `<head>`** — restringe execução mesmo se template fosse comprometido.
3. **`SecretStr` para a API key** — nunca em logs ou exceções.

Migrado de SMTP Gmail para a API do Resend (2026-07-21, decisão do dono):
`httpx` (já dependência do projeto, async-first) substitui `smtplib` bloqueante
— sem necessidade de `asyncio.to_thread`. Remetente exibido como "SefWorkStation
<RESEND_FROM_EMAIL>" (`RESEND_SENDER_NAME`). Preserva a semântica de privacidade
original: cada destinatário recebe uma chamada de API própria (`to` com um único
endereço) — nenhum destinatário vê o e-mail dos demais.
"""

from __future__ import annotations

import base64
import csv
import io
import json
from datetime import UTC
from typing import TYPE_CHECKING, Final, Literal

import httpx
import structlog
from jinja2 import Environment, PackageLoader, select_autoescape

from monitoritcd.notifiers.severity import emoji_for_tier, label_for_tier

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from monitoritcd.core.config import Settings
    from monitoritcd.core.models import Documento

logger = structlog.get_logger(__name__)

RESEND_API_URL: Final[str] = "https://api.resend.com/emails"
RESEND_SENDER_NAME: Final[str] = "SefWorkStation"
RESEND_TIMEOUT_SECONDS: Final[float] = 30.0

EmailMode = Literal["default", "compacto", "executivo", "newsletter"]

# Faixas horárias para saudação (#117), em horário BRT (UTC-3)
HORA_INICIO_MANHA: Final[int] = 5
HORA_INICIO_TARDE: Final[int] = 12
HORA_INICIO_NOITE: Final[int] = 18

TEMPLATE_BY_MODE: Final[dict[str, str]] = {
    "default": "email.html.j2",
    "compacto": "email_compacto.html.j2",
    "executivo": "email_executivo.html.j2",
    "newsletter": "email_newsletter.html.j2",
}

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

# Mapeamento de Topic → seção (para template newsletter, #114)
TOPIC_SECAO_LABEL: Final[dict[str, str]] = {
    "itcd": "ITCD / ITCMD / ITD (tributário)",
    "sucessoes": "Sucessões (Direito Civil)",
    "regime_bens": "Regime de Bens",
}


def build_jinja_env() -> Environment:
    """Constrói Jinja2 com autoescape obrigatório (anti-XSS)."""
    return Environment(
        loader=PackageLoader("monitoritcd.notifiers", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _saudacao_dinamica(now: datetime) -> str:
    """#117 — saudação por horário em PT-BR (timezone do BRT, UTC-3)."""
    # BRT = UTC-3; converter sem dependência externa
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    hour_brt = (now.hour - 3) % 24
    if HORA_INICIO_MANHA <= hour_brt < HORA_INICIO_TARDE:
        return "Bom dia."
    if HORA_INICIO_TARDE <= hour_brt < HORA_INICIO_NOITE:
        return "Boa tarde."
    return "Boa noite."


def _format_subject(template: str, *, count: int, date_str: str, label: str) -> str:
    """#110 — subject com placeholders simples ({count}, {date}, {label}).

    V13 (Pentest): troca `str.format` por `string.Template` para evitar
    format string introspection (ex: `{count.__class__.__mro__}`).
    `string.Template` aceita apenas `$name` e `${name}`, sem acesso a
    attrs/items.
    """
    import string  # noqa: PLC0415

    # Compatibilidade retroativa: aceita `{count}` (legacy) convertendo
    # para `$count`. Templates novos devem usar `$name` diretamente.
    converted = (
        template.replace("{count}", "$count")
        .replace("{date}", "$date")
        .replace("{label}", "$label")
    )
    return string.Template(converted).safe_substitute(count=count, date=date_str, label=label)


def _render_item_context(doc: Documento) -> dict[str, str]:
    """Constrói o contexto Jinja2 para um único item (sem modificar `original`)."""
    tier_value = doc.llm.severity_tier.value if doc.llm else "normal"
    tipo_value = doc.llm.tipo.value if doc.llm else "outro"
    resumo_curto = doc.llm.resumo if doc.llm else ""
    resumo_completo = doc.llm.resumo_completo if doc.llm and doc.llm.resumo_completo else ""
    return {
        "doc_id": doc.doc_id,
        "titulo": doc.original.titulo_raw,
        "url": doc.original.url,
        "resumo": resumo_completo or resumo_curto,
        "resumo_curto": resumo_curto,
        "uf": doc.source.uf,
        "tipo_label": TIPO_LABELS.get(tipo_value, tipo_value),
        "tier_emoji": emoji_for_tier(doc.llm.severity_tier) if doc.llm else "⚪",
        "tier_label": label_for_tier(doc.llm.severity_tier) if doc.llm else "—",
        "tier_color": TIER_COLORS.get(tier_value, "#666"),
        "data_pub": doc.original.data_publicacao.strftime("%d/%m/%Y")
        if doc.original.data_publicacao
        else "",
        "fonte_nome": doc.source.nome,
        "relevancia": str(doc.llm.relevancia) if doc.llm else "—",
        "pontos_chave": " · ".join(doc.llm.pontos_chave) if doc.llm else "",
        "motivo_relevancia": doc.llm.motivo_relevancia if doc.llm else "",
        "contexto": doc.llm.contexto if doc.llm and doc.llm.contexto else "",
        "assuntos_relacionados": ", ".join(doc.llm.assuntos_relacionados) if doc.llm else "",
        "topics": ", ".join(doc.llm.topics) if doc.llm else "",
    }


def _build_ranking(items: list[dict[str, str]], top_n: int = 5) -> list[dict[str, str]]:
    """#103 — ranking dos top N por relevância (decrescente)."""

    def sort_key(it: dict[str, str]) -> int:
        try:
            return -int(it.get("relevancia", "0"))
        except ValueError:
            return 0

    return sorted(items, key=sort_key)[:top_n]


def _agrupar_por_topic(
    docs: Sequence[Documento],
    items: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """#114 — agrupa itens por topic principal para template newsletter."""
    secoes: dict[str, list[dict[str, str]]] = {}
    for doc, item in zip(docs, items, strict=True):
        topics = doc.llm.topics if doc.llm and doc.llm.topics else doc.source.topics
        # topics agora são strings (suporte a topics dinâmicos via /topicos)
        topic_key = topics[0] if topics else "itcd"
        secao_label = TOPIC_SECAO_LABEL.get(topic_key, topic_key)
        secoes.setdefault(secao_label, []).append(item)
    return secoes


def _build_context(
    docs: Sequence[Documento],
    *,
    digest_label: str,
    data_geracao: datetime,
    subject: str,
    bot_url: str | None,
    dashboard_url: str | None,
    repo_url: str | None,
    mostrar_unsubscribe: bool,
) -> dict[str, object]:
    """Contexto comum para todos os templates."""
    items = [_render_item_context(d) for d in docs]
    ranking = _build_ranking(items, top_n=5)
    criticos = sum(1 for it in items if it["tier_emoji"] == "🔴")
    altos = sum(1 for it in items if it["tier_emoji"] == "🟠")
    ufs = ", ".join(sorted({it["uf"] for it in items if it["uf"] != "_federal"}))

    return {
        "items": items,
        "ranking": ranking,
        "secoes": _agrupar_por_topic(docs, items),
        "digest_label": digest_label,
        "data_geracao": data_geracao.strftime("%d/%m/%Y %H:%M"),
        "subject": subject,
        "saudacao": _saudacao_dinamica(data_geracao),
        "criticos": criticos,
        "altos": altos,
        "ufs": ufs,
        "bot_url": bot_url,
        "dashboard_url": dashboard_url,
        "repo_url": repo_url,
        "mostrar_unsubscribe": mostrar_unsubscribe,
    }


def render_email(
    docs: Sequence[Documento],
    *,
    digest_label: str,
    data_geracao: datetime,
    subject: str | None = None,
    subject_template: str | None = None,
    mode: EmailMode = "default",
    env: Environment | None = None,
    bot_url: str | None = None,
    dashboard_url: str | None = None,
    repo_url: str | None = None,
    mostrar_unsubscribe: bool = True,
) -> tuple[str, str]:
    """Renderiza assunto + corpo HTML.

    Args:
        docs: documentos a incluir.
        digest_label: rótulo (ex: "Diário", "Semanal", "Mensal").
        data_geracao: timestamp do digest.
        subject: assunto pronto; ignora `subject_template` se fornecido.
        subject_template: template com placeholders {count}, {date}, {label}. (#110)
        mode: variante de template — default, compacto, executivo, newsletter.
        env: Jinja2 environment (injectable para testes).
        bot_url, dashboard_url, repo_url: links no footer (#108, #115).
        mostrar_unsubscribe: nota de "como desativar" no footer (#119).

    Returns:
        (subject, body_html)
    """
    env = env or build_jinja_env()
    count = len(docs)
    date_str = data_geracao.strftime("%d/%m/%Y")

    if subject is None:
        if subject_template:
            final_subject = _format_subject(
                subject_template,
                count=count,
                date_str=date_str,
                label=digest_label,
            )
        else:
            unidade = "novidade" if count == 1 else "novidades"
            final_subject = f"[MonitorITCD] {digest_label} — {count} {unidade}"
    else:
        final_subject = subject

    template_name = TEMPLATE_BY_MODE.get(mode, TEMPLATE_BY_MODE["default"])
    template = env.get_template(template_name)
    context = _build_context(
        docs,
        digest_label=digest_label,
        data_geracao=data_geracao,
        subject=final_subject,
        bot_url=bot_url,
        dashboard_url=dashboard_url,
        repo_url=repo_url,
        mostrar_unsubscribe=mostrar_unsubscribe,
    )
    body = template.render(**context)
    return final_subject, body


def build_csv_attachment(docs: Sequence[Documento]) -> bytes:
    """#106 — Gera CSV dos itens (UTF-8 com BOM para abrir no Excel)."""
    output = io.StringIO()
    output.write("﻿")  # BOM
    writer = csv.writer(output, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
            "doc_id",
            "uf",
            "tipo",
            "tier",
            "relevancia",
            "data_pub",
            "fonte",
            "titulo",
            "url",
            "resumo",
            "resumo_completo",
            "pontos_chave",
            "assuntos_relacionados",
        ]
    )
    for d in docs:
        tier = d.llm.severity_tier.value if d.llm else ""
        tipo = d.llm.tipo.value if d.llm else ""
        relevancia = str(d.llm.relevancia) if d.llm else ""
        resumo = d.llm.resumo if d.llm else ""
        resumo_completo = d.llm.resumo_completo if d.llm else ""
        pontos_chave = " | ".join(d.llm.pontos_chave) if d.llm else ""
        assuntos_relacionados = " | ".join(d.llm.assuntos_relacionados) if d.llm else ""
        data_pub = d.original.data_publicacao.isoformat() if d.original.data_publicacao else ""
        writer.writerow(
            [
                d.doc_id,
                d.source.uf,
                tipo,
                tier,
                relevancia,
                data_pub,
                d.source.nome,
                d.original.titulo_raw,
                d.original.url,
                resumo,
                resumo_completo,
                pontos_chave,
                assuntos_relacionados,
            ]
        )
    return output.getvalue().encode("utf-8")


def build_json_attachment(docs: Sequence[Documento]) -> bytes:
    """#107 — Gera JSON estruturado dos itens."""
    payload = [
        {
            "doc_id": d.doc_id,
            "uf": d.source.uf,
            "fonte": d.source.nome,
            "url": d.original.url,
            "titulo": d.original.titulo_raw,
            "data_publicacao": (
                d.original.data_publicacao.isoformat() if d.original.data_publicacao else None
            ),
            "tipo": d.llm.tipo.value if d.llm else None,
            "severity_tier": d.llm.severity_tier.value if d.llm else None,
            "relevancia": d.llm.relevancia if d.llm else None,
            "resumo": d.llm.resumo if d.llm else None,
            "resumo_completo": d.llm.resumo_completo if d.llm else None,
            "pontos_chave": d.llm.pontos_chave if d.llm else [],
            "motivo_relevancia": d.llm.motivo_relevancia if d.llm else None,
            "assuntos_relacionados": d.llm.assuntos_relacionados if d.llm else [],
            "tags": d.llm.tags if d.llm else [],
            "topics": d.llm.topics if d.llm else [],
            "metadados_extraidos": d.llm.metadados_extraidos if d.llm else {},
            "search_terms": d.search_index.terms if d.search_index else [],
        }
        for d in docs
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _build_resend_payload(
    *,
    from_email: str,
    recipient: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    reply_to: str | None = None,
    attachments: Sequence[tuple[str, str, bytes]] | None = None,
) -> dict[str, object]:
    """Monta o payload JSON da API do Resend para UM destinatário (`to` só ele).

    Args:
        attachments: sequência de (filename, mimetype, content_bytes) — mimetype
            não é usado pelo Resend (infere pelo filename), mantido na assinatura
            só por compatibilidade com os chamadores existentes.
    """
    payload: dict[str, object] = {
        "from": f"{RESEND_SENDER_NAME} <{from_email}>",
        "to": [recipient],
        "subject": subject,
        "html": body_html,
    }
    if body_text:
        payload["text"] = body_text
    if reply_to:
        payload["reply_to"] = reply_to
    if attachments:
        payload["attachments"] = [
            {"filename": filename, "content": base64.b64encode(content).decode("ascii")}
            for filename, _mimetype, content in attachments
        ]
    return payload


async def _send_via_resend(
    *,
    api_key: str,
    from_email: str,
    recipient: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    reply_to: str | None = None,
    attachments: Sequence[tuple[str, str, bytes]] | None = None,
) -> None:
    """Envia para 1 destinatário via API do Resend (`POST /emails`)."""
    payload = _build_resend_payload(
        from_email=from_email,
        recipient=recipient,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        reply_to=reply_to,
        attachments=attachments,
    )
    async with httpx.AsyncClient(timeout=RESEND_TIMEOUT_SECONDS) as client:
        response = await client.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        response.raise_for_status()


async def _send_via_resend_many(
    *,
    api_key: str,
    from_email: str,
    recipients: Sequence[str],
    subject: str,
    body_html: str,
    body_text: str | None = None,
    reply_to: str | None = None,
    attachments: Sequence[tuple[str, str, bytes]] | None = None,
) -> tuple[int, list[str]]:
    """Envia individualmente a cada destinatário, uma chamada de API por vez.

    Cada destinatário recebe uma mensagem com `to` apenas ele — o Resend nunca
    vê os e-mails uns dos outros na mesma chamada. Falha em um não aborta os
    demais (mesma semântica do envio via SMTP que este substitui).

    Returns:
        (enviados_ok, lista de destinatários que falharam).
    """
    enviados = 0
    falhas: list[str] = []
    for recipient in recipients:
        try:
            await _send_via_resend(
                api_key=api_key,
                from_email=from_email,
                recipient=recipient,
                subject=subject,
                body_html=body_html,
                body_text=body_text,
                reply_to=reply_to,
                attachments=attachments,
            )
            enviados += 1
        except httpx.HTTPError as e:
            logger.warning("email.recipient_failed", error=str(e))
            falhas.append(recipient)
    return enviados, falhas


class EmailNotifier:
    """Notificador por e-mail via API do Resend."""

    def __init__(self, settings: Settings, env: Environment | None = None) -> None:
        self._settings = settings
        self._env = env or build_jinja_env()

    async def send_digest(
        self,
        docs: Sequence[Documento],
        *,
        digest_label: str,
        data_geracao: datetime,
        mode: EmailMode = "default",
        subject_template: str | None = None,
        attach_csv: bool = False,
        attach_json: bool = False,
        bot_url: str | None = None,
        dashboard_url: str | None = None,
        repo_url: str | None = None,
        reply_to: str | None = None,
        recipients: Sequence[str] | None = None,
    ) -> None:
        """Envia digest com lista de docs.

        `recipients`: destinatários; default `[OWNER_EMAIL]`. Cada um recebe um
        e-mail individual (`To:` só ele) — privacidade entre inscritos.
        """
        subject, body = render_email(
            docs,
            digest_label=digest_label,
            data_geracao=data_geracao,
            subject_template=subject_template,
            mode=mode,
            env=self._env,
            bot_url=bot_url,
            dashboard_url=dashboard_url,
            repo_url=repo_url,
        )

        attachments: list[tuple[str, str, bytes]] = []
        if attach_csv:
            attachments.append(
                (
                    f"monitoritcd-{digest_label.lower()}.csv",
                    "text/csv",
                    build_csv_attachment(docs),
                )
            )
        if attach_json:
            attachments.append(
                (
                    f"monitoritcd-{digest_label.lower()}.json",
                    "application/json",
                    build_json_attachment(docs),
                )
            )

        destinatarios = list(dict.fromkeys(recipients or [self._settings.OWNER_EMAIL]))
        enviados, falhas = await _send_via_resend_many(
            api_key=self._settings.RESEND_API_KEY.get_secret_value(),
            from_email=self._settings.RESEND_FROM_EMAIL,
            recipients=destinatarios,
            subject=subject,
            body_html=body,
            reply_to=reply_to,
            attachments=attachments or None,
        )

        # Não logar e-mails em claro (dado pessoal) — só contagens.
        logger.info(
            "email.sent",
            recipients_count=len(destinatarios),
            enviados=enviados,
            falhas=len(falhas),
            count=len(docs),
            digest=digest_label,
            mode=mode,
            attachments=len(attachments),
        )
