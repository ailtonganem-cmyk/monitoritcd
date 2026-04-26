"""Handlers dos comandos do bot.

Cada handler:
- Recebe `BotContext` com storage e settings.
- Valida argumentos via pydantic.
- Retorna `HandlerResult` com texto a enviar.

Nenhum handler faz I/O direto com Telegram — a camada de webhook que envia.
Permite testar handlers sem mock de HTTP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from monitoritcd.bot.audit import log_bot_action
from monitoritcd.bot.auth import (
    InvalidConfirmationTokenError,
    TwoStepConfirmation,
)
from monitoritcd.core import limits
from monitoritcd.core.models import StatusDocumento, Topic

if TYPE_CHECKING:
    from monitoritcd.core.config import Settings
    from monitoritcd.storage.base import StorageProtocol

# Regex para argumentos válidos (Princípio 1: backend nunca confia)
UF_ARG_REGEX = re.compile(r"^[A-Z]{2}$")
DURATION_REGEX = re.compile(limits.DURATION_REGEX)

MAX_BOT_ARGS = 10
MIN_ARGS_WITH_UF = 2  # subcomando + UF
MIN_PATTERN_LENGTH = 3  # termo mínimo de watch list


@dataclass
class HandlerResult:
    """Resposta de um handler. `text` é enviado ao chat."""

    text: str
    is_error: bool = False


@dataclass
class BotContext:
    """Contexto compartilhado entre handlers."""

    settings: Settings
    storage: StorageProtocol
    confirmation: TwoStepConfirmation


@dataclass
class ParsedCommand:
    """Comando parseado: nome + argumentos."""

    name: str
    args: list[str]


def parse_command(text: str) -> ParsedCommand | None:
    """Parseia texto em ParsedCommand. Retorna None se não é comando.

    Aplica `MAX_BOT_COMMAND_LENGTH` enforcement.
    """
    if not text:
        return None
    if len(text) > limits.MAX_BOT_COMMAND_LENGTH:
        msg = f"comando excede MAX_BOT_COMMAND_LENGTH ({limits.MAX_BOT_COMMAND_LENGTH})"
        raise ValueError(msg)

    text = text.strip()
    if not text.startswith("/"):
        return None

    parts = text.split()
    name = parts[0][1:].lower()  # remove `/`
    # Telegram pode anexar @botname — normalizar
    name = name.split("@")[0]

    args = parts[1:]
    if len(args) > MAX_BOT_ARGS:
        msg = "muitos argumentos"
        raise ValueError(msg)
    for arg in args:
        if len(arg) > limits.MAX_BOT_ARG_LENGTH:
            msg = f"argumento excede MAX_BOT_ARG_LENGTH ({limits.MAX_BOT_ARG_LENGTH})"
            raise ValueError(msg)

    return ParsedCommand(name=name, args=args)


# ─────────────────────────────────────────────────────────────────────────────
# Handlers (cada um recebe ctx + ParsedCommand, retorna HandlerResult)
# ─────────────────────────────────────────────────────────────────────────────


async def handle_start(_ctx: BotContext, _cmd: ParsedCommand) -> HandlerResult:
    return HandlerResult(
        text=(
            "👋 *MonitorITCD* — bot pessoal\n\n"
            "🗂️ *Divisões temáticas*:\n"
            "• ITCD/ITCMD/ITD (tributário)\n"
            "• Direito das Sucessões (CC 1.784+)\n"
            "• Regime de Bens (CC 1.639-1.688)\n\n"
            "📡 *Cobertura*: 27 UFs (Assembleias, SEFAZs, DOEs) + LexML federal "
            "+ STF + STJ + TRFs (1-6) + CNJ + TJs estaduais (SP/RJ/MG).\n\n"
            "*Comandos*:\n"
            "• /help — lista de comandos\n"
            "• /status — saúde do sistema\n"
            "• /buscar <termo> [topico=...] — busca no histórico\n"
            "• /topicos — lista divisões temáticas\n"
            "• /observar <termo> | listar | remover <id>\n"
            "• /marcar <doc_id_prefix> <tag> — tag pessoal num doc\n"
            "• /relatorio [diario|semanal] — digest sob demanda\n"
            "• /estados listar — UFs ativas\n"
            "• /estados ativar <UF>\n"
            "• /estados desativar <UF> (requer confirmação)\n"
            "• /confirmar <token>\n"
        ),
    )


async def handle_help(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    return await handle_start(ctx, cmd)


async def handle_status(ctx: BotContext, _cmd: ParsedCommand) -> HandlerResult:
    docs = await ctx.storage.list_documentos(limit=1000)
    pending = sum(1 for d in docs if d.status == StatusDocumento.PENDING)
    classified = sum(1 for d in docs if d.status == StatusDocumento.CLASSIFIED)
    notified = sum(1 for d in docs if d.status == StatusDocumento.NOTIFIED)

    active = await ctx.storage.get_active_states()
    active_count = len(active.active_uf) if active else 0

    return HandlerResult(
        text=(
            f"📊 *Status*\n"
            f"• Documentos: {len(docs)} total\n"
            f"  - pending: {pending}\n"
            f"  - classified: {classified}\n"
            f"  - notified: {notified}\n"
            f"• UFs ativas: {active_count}\n"
        ),
    )


async def handle_buscar(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if not cmd.args:
        return HandlerResult(
            text="❌ Uso: /buscar <termo> [topico=itcd|sucessoes|regime_bens]", is_error=True
        )

    # Separa argumentos: termos vs filtros (topico=...)
    termos: list[str] = []
    topic_filter: Topic | None = None
    for arg in cmd.args:
        if arg.startswith("topico="):
            try:
                topic_filter = Topic(arg.split("=", 1)[1].lower())
            except ValueError:
                return HandlerResult(
                    text=f"❌ Tópico inválido: '{arg}'. Válidos: itcd, sucessoes, regime_bens",
                    is_error=True,
                )
        else:
            termos.append(arg)

    if not termos:
        return HandlerResult(text="❌ Forneça pelo menos um termo de busca.", is_error=True)

    termo = " ".join(termos).lower()
    docs = await ctx.storage.list_documentos(limit=200)
    matched = []
    for d in docs:
        text_match = termo in d.original.titulo_raw.lower() or (
            d.llm is not None and termo in d.llm.resumo.lower()
        )
        topic_match = topic_filter is None or (d.llm is not None and topic_filter in d.llm.topics)
        if text_match and topic_match:
            matched.append(d)

    if not matched:
        suffix = f" no tópico {topic_filter.value}" if topic_filter else ""
        return HandlerResult(text=f"🔍 Nenhum resultado para '{termo}'{suffix}.")

    header = f"🔍 {len(matched)} resultado(s) para '{termo}'"
    if topic_filter:
        header += f" (tópico: {topic_filter.value})"
    lines = [header + ":"]
    for d in matched[:10]:
        topics_str = ""
        if d.llm and d.llm.topics:
            topics_str = " " + "·".join(t.value[:3] for t in d.llm.topics)
        lines.append(f"• [{d.source.uf}{topics_str}] {d.original.titulo_raw}")
    return HandlerResult(text="\n".join(lines))


async def handle_topicos(_ctx: BotContext, _cmd: ParsedCommand) -> HandlerResult:
    return HandlerResult(
        text=(
            "🗂️ *Divisões temáticas do sistema*:\n\n"
            "• `itcd` — Imposto sobre Transmissão Causa Mortis e Doação\n"
            "  (alíquotas, fato gerador, IN, portarias, GIA-ITCMD)\n\n"
            "• `sucessoes` — Direito Civil das Sucessões (CC 1.784+)\n"
            "  (herança, testamento, inventário, legítima, herdeiros, partilha)\n\n"
            "• `regime_bens` — Regime de Bens (CC 1.639-1.688)\n"
            "  (comunhão parcial/universal, separação, pacto antenupcial, Súmula 377)\n\n"
            "Use `/buscar <termo> topico=<area>` para filtrar por tópico."
        ),
    )


async def _handle_estados_listar(ctx: BotContext) -> HandlerResult:
    active = await ctx.storage.get_active_states()
    if not active or not active.active_uf:
        return HandlerResult(text="📋 Nenhuma UF ativa.")
    return HandlerResult(text=f"📋 UFs ativas: {', '.join(sorted(active.active_uf))}")


async def _handle_estados_ativar(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if len(cmd.args) < MIN_ARGS_WITH_UF:
        return HandlerResult(text="❌ Uso: /estados ativar <UF>", is_error=True)
    uf = cmd.args[1]
    if not UF_ARG_REGEX.match(uf):
        return HandlerResult(text=f"❌ UF inválida: '{uf}'", is_error=True)
    await log_bot_action(ctx, action="bot.estados.ativar", payload={"uf": uf})
    return HandlerResult(text=f"✅ UF {uf} marcada para ativação.")


async def _handle_estados_desativar(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if len(cmd.args) < MIN_ARGS_WITH_UF:
        return HandlerResult(text="❌ Uso: /estados desativar <UF>", is_error=True)
    uf = cmd.args[1]
    if not UF_ARG_REGEX.match(uf):
        return HandlerResult(text=f"❌ UF inválida: '{uf}'", is_error=True)
    token = ctx.confirmation.issue(f"estados.desativar:{uf}")
    await log_bot_action(
        ctx,
        action="bot.estados.desativar.token",
        payload={"uf": uf, "token_prefix": token[:4]},
    )
    return HandlerResult(
        text=(f"⚠️ Confirmar desativação de {uf}?\nUse `/confirmar {token}` em até 60s."),
    )


_ESTADOS_SUBHANDLERS = {
    "listar": lambda ctx, _cmd: _handle_estados_listar(ctx),
    "ativar": _handle_estados_ativar,
    "desativar": _handle_estados_desativar,
}


async def handle_estados(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if not cmd.args:
        return HandlerResult(text="❌ Uso: /estados <listar|ativar|desativar> [UF]", is_error=True)
    sub = cmd.args[0].lower()
    handler = _ESTADOS_SUBHANDLERS.get(sub)
    if handler is None:
        return HandlerResult(text=f"❌ Subcomando desconhecido: '{sub}'", is_error=True)
    return await handler(ctx, cmd)


async def handle_confirmar(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if not cmd.args:
        return HandlerResult(text="❌ Uso: /confirmar <token>", is_error=True)
    token = cmd.args[0]
    # find_action descobre a ação sem consumir; depois consume valida e remove.
    action = ctx.confirmation.find_action(token)
    if action is None:
        return HandlerResult(text="❌ Token inválido ou expirado.", is_error=True)
    try:
        ctx.confirmation.consume(token, action)
    except InvalidConfirmationTokenError:
        return HandlerResult(text="❌ Token inválido ou expirado.", is_error=True)
    await log_bot_action(
        ctx,
        action="bot.confirmar",
        payload={"confirmed_action": action},
    )
    return HandlerResult(text=f"✅ Ação '{action}' confirmada.")


# ─────────────────────────────────────────────────────────────────────────────
# Watch list
# ─────────────────────────────────────────────────────────────────────────────


async def _watch_listar(ctx: BotContext) -> HandlerResult:
    watches = await ctx.storage.list_watches()
    if not watches:
        return HandlerResult(text="📋 Nenhum watch ativo.")
    lines = [f"📋 {len(watches)} watch(es) ativo(s):"]
    for w in watches[:20]:
        lines.append(
            f"• [{w.watch_id[:8]}] '{w.pattern}' ({w.pattern_type}, rel≥{w.relevancia_min})"
        )
    return HandlerResult(text="\n".join(lines))


async def _watch_adicionar(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if len(cmd.args) < MIN_ARGS_WITH_UF:
        return HandlerResult(
            text="❌ Uso: /observar <termo>\nEx: /observar holding familiar SP",
            is_error=True,
        )
    pattern = " ".join(cmd.args[1:])
    if len(pattern) < MIN_PATTERN_LENGTH:
        return HandlerResult(text="❌ Termo muito curto (mínimo 3 chars).", is_error=True)

    from datetime import UTC, datetime  # noqa: PLC0415
    from uuid import uuid4  # noqa: PLC0415

    from monitoritcd.core.models import Watch  # noqa: PLC0415

    watch = Watch(
        owner_id=ctx.settings.OWNER_ID,
        watch_id=uuid4().hex[:16],
        pattern=pattern,
        pattern_type="term",
        relevancia_min=5,
        cooldown_hours=24,
        created_at=datetime.now(UTC),
    )
    try:
        await ctx.storage.save_watch(watch)
    except (ValueError, RuntimeError) as e:
        await log_bot_action(
            ctx,
            action="bot.observar.add",
            payload={"pattern": pattern},
            result="failure",
            error=str(e),
        )
        return HandlerResult(text=f"❌ Erro: {e}", is_error=True)
    await log_bot_action(
        ctx,
        action="bot.observar.add",
        payload={"watch_id": watch.watch_id, "pattern": pattern},
    )
    return HandlerResult(
        text=f"✅ Watch criado: '{pattern}' (id={watch.watch_id[:8]})",
    )


async def _watch_remover(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if len(cmd.args) < MIN_ARGS_WITH_UF:
        return HandlerResult(text="❌ Uso: /observar remover <id>", is_error=True)
    watch_id_prefix = cmd.args[1]
    watches = await ctx.storage.list_watches()
    matches = [w for w in watches if w.watch_id.startswith(watch_id_prefix)]
    if not matches:
        return HandlerResult(text=f"❌ Watch não encontrado: {watch_id_prefix}", is_error=True)
    if len(matches) > 1:
        return HandlerResult(
            text=f"❌ Ambíguo: {len(matches)} matches. Use prefixo maior.",
            is_error=True,
        )
    await ctx.storage.delete_watch(matches[0].watch_id)
    await log_bot_action(
        ctx,
        action="bot.observar.remove",
        payload={"watch_id": matches[0].watch_id, "pattern": matches[0].pattern},
    )
    return HandlerResult(text=f"✅ Watch removido: '{matches[0].pattern}'")


_OBSERVAR_SUBHANDLERS = {
    "listar": lambda ctx, _cmd: _watch_listar(ctx),
    "remover": _watch_remover,
}


async def handle_observar(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    """`/observar <termo>` cria; `/observar listar`; `/observar remover <id>`."""
    if not cmd.args:
        return HandlerResult(
            text="❌ Uso: /observar <termo> | /observar listar | /observar remover <id>",
            is_error=True,
        )
    sub = cmd.args[0].lower()
    if sub in _OBSERVAR_SUBHANDLERS:
        return await _OBSERVAR_SUBHANDLERS[sub](ctx, cmd)
    # Default: o argumento eh o termo (criacao implicita)
    return await _watch_adicionar(
        ctx, ParsedCommand(name="observar", args=["adicionar", *cmd.args])
    )


# ─────────────────────────────────────────────────────────────────────────────
# /marcar
# ─────────────────────────────────────────────────────────────────────────────


async def handle_marcar(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:  # noqa: PLR0911
    """`/marcar <doc_id_prefix> <tag>` — adiciona tag pessoal ao documento.

    `doc_id_prefix` é o prefixo do doc_id (mostrado em buscas/digests);
    se ambíguo, retorna erro. Tag idempotente (re-marcar não duplica).
    """
    if len(cmd.args) < MIN_ARGS_WITH_UF:
        return HandlerResult(
            text="❌ Uso: /marcar <doc_id_prefix> <tag>",
            is_error=True,
        )
    doc_prefix = cmd.args[0]
    tag = " ".join(cmd.args[1:]).strip()
    if not tag:
        return HandlerResult(text="❌ Tag vazia.", is_error=True)
    if len(tag) > limits.MAX_TAG_LENGTH:
        return HandlerResult(
            text=f"❌ Tag muito longa (máximo {limits.MAX_TAG_LENGTH} caracteres).",
            is_error=True,
        )

    docs = await ctx.storage.list_documentos(limit=1000)
    matches = [d for d in docs if d.doc_id.startswith(doc_prefix)]
    if not matches:
        return HandlerResult(
            text=f"❌ Documento não encontrado com prefixo '{doc_prefix}'.",
            is_error=True,
        )
    if len(matches) > 1:
        return HandlerResult(
            text=f"❌ Ambíguo: {len(matches)} documentos batem. Use prefixo maior.",
            is_error=True,
        )

    doc = matches[0]
    try:
        await ctx.storage.add_user_tag(doc.doc_id, tag)
    except (ValueError, RuntimeError) as e:
        await log_bot_action(
            ctx,
            action="bot.marcar",
            payload={"doc_id": doc.doc_id, "tag": tag},
            result="failure",
            error=str(e),
        )
        return HandlerResult(text=f"❌ Erro ao marcar: {e}", is_error=True)

    await log_bot_action(
        ctx,
        action="bot.marcar",
        payload={"doc_id": doc.doc_id, "tag": tag},
    )
    titulo = doc.original.titulo_raw[:60]
    return HandlerResult(text=f"✅ Tag '{tag}' adicionada ao doc '{titulo}'.")


# ─────────────────────────────────────────────────────────────────────────────
# /relatorio
# ─────────────────────────────────────────────────────────────────────────────


async def handle_relatorio(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    """`/relatorio [diario|semanal]` — digest sob demanda do período.

    Lista documentos NOTIFIED ou CLASSIFIED no período (default: 1 dia).
    Não envia digest pelo Telegram — apenas resume na resposta inline.
    """
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    periodo = (cmd.args[0].lower() if cmd.args else "diario").strip()
    if periodo not in {"diario", "semanal"}:
        return HandlerResult(
            text="❌ Período inválido. Use: /relatorio [diario|semanal]",
            is_error=True,
        )

    dias = 1 if periodo == "diario" else 7
    since = datetime.now(UTC) - timedelta(days=dias)
    docs = await ctx.storage.list_documentos(since=since, limit=1000)

    if not docs:
        return HandlerResult(text=f"📊 Nenhum documento nos últimos {dias} dia(s).")

    # Resumo por severity tier
    tier_counts: dict[str, int] = {}
    for d in docs:
        if d.llm:
            tier = d.llm.severity_tier.value
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

    label = "Diário" if periodo == "diario" else "Semanal"
    lines = [f"📊 Relatório {label} ({len(docs)} documentos)"]
    for tier, count in sorted(tier_counts.items()):
        lines.append(f"• {tier}: {count}")

    # Top 5 documentos por relevância
    rated = sorted(
        (d for d in docs if d.llm is not None),
        key=lambda d: d.llm.relevancia if d.llm else 0,  # type: ignore[union-attr]
        reverse=True,
    )[:5]
    if rated:
        lines.append("\nTop 5 por relevância:")
        for d in rated:
            rel = d.llm.relevancia if d.llm else 0
            titulo = d.original.titulo_raw[:50]
            lines.append(f"• [{d.doc_id[:8]}] rel={rel} — {titulo}")

    return HandlerResult(text="\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────────


HANDLERS = {
    "start": handle_start,
    "help": handle_help,
    "status": handle_status,
    "buscar": handle_buscar,
    "topicos": handle_topicos,
    "estados": handle_estados,
    "confirmar": handle_confirmar,
    "observar": handle_observar,
    "marcar": handle_marcar,
    "relatorio": handle_relatorio,
}


async def dispatch(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    """Dispatch para handler correspondente. Retorna erro se desconhecido."""
    handler = HANDLERS.get(cmd.name)
    if handler is None:
        return HandlerResult(text=f"❌ Comando desconhecido: /{cmd.name}", is_error=True)
    return await handler(ctx, cmd)
