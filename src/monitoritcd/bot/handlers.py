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
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from monitoritcd.bot.audit import log_bot_action
from monitoritcd.bot.auth import (
    InvalidConfirmationTokenError,
    TwoStepConfirmation,
)
from monitoritcd.core import limits
from monitoritcd.core.models import (
    DEFAULT_TOPIC_IDS,
    ExtraKeywordsConfig,
    ExtraTopicsConfig,
    SeverityTier,
    StatusDocumento,
    TipoAto,
    TopicEntry,
)
from monitoritcd.filters.keywords import KEYWORDS_DEFAULT
from monitoritcd.notifiers.telegram_notifier import render_telegram
from monitoritcd.search import document_search_corpus, normalize_search_query
from monitoritcd.security.markdown_escape import escape_markdown_v2, safe_link

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
    """Resposta de um handler. `text` é enviado ao chat.

    Quando `pre_escaped=True`, o webhook/poller não aplica `escape_markdown_v2`
    sobre o texto: o handler é responsável por entregar MarkdownV2 válido,
    permitindo links clicáveis (`[label](url)`) e formatação rica.
    """

    text: str
    is_error: bool = False
    pre_escaped: bool = False


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
            "• /buscar <termos> [uf=XX] [ano=YYYY] [topico=...] [tipo=...]\n"
            "          [severidade=...] [limite=N] — busca com links clicáveis\n"
            "• /topicos listar | adicionar <id> <descrição> | remover <id>\n"
            "          — divisões temáticas dinâmicas (LLM classifica)\n"
            "• /temas listar | adicionar <termo> [topico=...] | remover | reset\n"
            "          — gerencia keywords extras de busca\n"
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


_BUSCAR_DEFAULT_LIMIT = 10
_BUSCAR_MAX_LIMIT = 50
_BUSCAR_SCAN_LIMIT = 5000  # limite defensivo de varredura no backend de busca
_BUSCAR_RESUMO_PREVIEW = 220
_BUSCAR_MIN_YEAR = 2020
_BUSCAR_MAX_YEAR = 2099

_SEVERITY_EMOJI = {
    SeverityTier.CRITICO: "🔴",
    SeverityTier.ALTA: "🟠",
    SeverityTier.NORMAL: "🟡",
    SeverityTier.BAIXA: "🟢",
}


@dataclass
class _BuscarFilters:
    """Filtros parseados do comando /buscar. Acessados por _apply_filters."""

    termos: list[str]
    uf: str | None = None
    ano: int | None = None
    topico: str | None = None
    tipo: TipoAto | None = None
    severidade: SeverityTier | None = None
    limite: int = _BUSCAR_DEFAULT_LIMIT


def _parse_buscar_filters(args: list[str]) -> _BuscarFilters | str:  # noqa: PLR0911, PLR0912
    """Parseia args do /buscar. Retorna filtros válidos ou mensagem de erro PT-BR.

    Many returns/branches são intencionais: cada filtro tem mensagem PT-BR
    específica. Refator para dicionário de validators dificultaria a legibilidade
    sem benefício real (todas as branches são "case-like").
    """
    termos: list[str] = []
    f = _BuscarFilters(termos=termos)
    for arg in args:
        if "=" not in arg:
            termos.append(arg)
            continue
        key, _, raw_value = arg.partition("=")
        key = key.lower()
        value = raw_value.strip()
        if not value:
            return f"❌ Filtro `{key}=` vazio."
        try:
            if key == "uf":
                v = value.upper()
                if v == "_FEDERAL":
                    f.uf = "_federal"
                elif v in limits.VALID_UFS:
                    f.uf = v
                else:
                    return (
                        f"❌ UF inválida: `{value}`. "
                        f"Use 2 letras de UF brasileira (ex: PR) ou `_federal`."
                    )
            elif key == "ano":
                year = int(value)
                if not (_BUSCAR_MIN_YEAR <= year <= _BUSCAR_MAX_YEAR):
                    return f"❌ Ano fora do intervalo {_BUSCAR_MIN_YEAR}-{_BUSCAR_MAX_YEAR}."
                f.ano = year
            elif key == "topico":
                topic_id = value.lower()
                if not _TOPIC_ID_REGEX.fullmatch(topic_id):
                    return f"❌ Tópico inválido: `{value}`. Use letras minúsculas, dígitos e `_`."
                f.topico = topic_id
            elif key == "tipo":
                try:
                    f.tipo = TipoAto(value.lower())
                except ValueError:
                    return (
                        f"❌ Tipo inválido: `{value}`. Válidos: "
                        f"projeto_lei, lei_sancionada, decreto, instrucao_normativa, "
                        f"portaria, noticia, jurisprudencia, doutrina, outro."
                    )
            elif key == "severidade":
                try:
                    f.severidade = SeverityTier(value.lower())
                except ValueError:
                    return (
                        f"❌ Severidade inválida: `{value}`. Válidas: critico, alta, normal, baixa."
                    )
            elif key == "limite":
                lim = int(value)
                if not (1 <= lim <= _BUSCAR_MAX_LIMIT):
                    return f"❌ `limite` deve estar entre 1 e {_BUSCAR_MAX_LIMIT}."
                f.limite = lim
            else:
                return f"❌ Filtro desconhecido: `{key}`."
        except ValueError:
            return f"❌ Valor inválido para `{key}`: `{value}`."
    return f


def _matches_text(termos: list[str], doc: object) -> bool:
    """Termo livre: AND de substrings no corpus pesquisável materializado."""
    if not termos:
        return True
    haystack = document_search_corpus(doc)  # type: ignore[arg-type]
    return all(normalize_search_query(t) in haystack for t in termos)


def _format_buscar_card(doc: object) -> str:
    """Renderiza um resultado em MarkdownV2 (link clicável + meta + resumo curto)."""
    titulo = doc.original.titulo_raw or "(sem título)"  # type: ignore[attr-defined]
    url = doc.original.url or ""  # type: ignore[attr-defined]
    link = safe_link(titulo, url) if url else f"*{escape_markdown_v2(titulo)}*"

    uf_str = escape_markdown_v2(doc.source.uf or "?")  # type: ignore[attr-defined]
    meta_parts = [uf_str]
    if doc.llm is not None:  # type: ignore[attr-defined]
        emoji = _SEVERITY_EMOJI.get(doc.llm.severity_tier, "")  # type: ignore[attr-defined]
        if emoji:
            sev = escape_markdown_v2(doc.llm.severity_tier.value)  # type: ignore[attr-defined]
            meta_parts.append(f"{emoji} {sev}")
        tipo = escape_markdown_v2(doc.llm.tipo.value)  # type: ignore[attr-defined]
        meta_parts.append(tipo)
    fetched = doc.original.fetched_at  # type: ignore[attr-defined]
    if fetched:
        meta_parts.append(escape_markdown_v2(fetched.strftime("%Y-%m-%d")))
    meta = " · ".join(meta_parts)

    resumo_line = ""
    if doc.llm is not None and doc.llm.resumo:  # type: ignore[attr-defined]
        resumo = doc.llm.resumo_completo or doc.llm.resumo  # type: ignore[attr-defined]
        snippet = resumo[:_BUSCAR_RESUMO_PREVIEW]
        if len(resumo) > _BUSCAR_RESUMO_PREVIEW:
            snippet += "…"
        resumo_line = f"\n  _{escape_markdown_v2(snippet)}_"

    return f"• {link}\n  {meta}{resumo_line}"


async def handle_buscar(  # noqa: PLR0912, PLR0915
    ctx: BotContext, cmd: ParsedCommand
) -> HandlerResult:
    """Repositório pesquisável de notícias coletadas.

    Sintaxe:
        /buscar <termos...> [uf=XX] [ano=YYYY] [topico=...] [tipo=...]
                            [severidade=...] [limite=N]

    Termos são combinados em AND. Filtros UF e ano são aplicados no Firestore;
    demais aplicam-se localmente sobre até `_BUSCAR_FIRESTORE_FETCH` documentos.
    Resposta usa MarkdownV2 com links clicáveis (`pre_escaped=True`).
    """
    if not cmd.args:
        return HandlerResult(
            text=(
                "❌ Uso: `/buscar <termos> [uf=XX] [ano=YYYY] "
                "[topico=itcd|sucessoes|regime_bens] [tipo=lei_sancionada|projeto_lei|...] "
                "[severidade=critico|alta|normal|baixa] [limite=N]`"
            ),
            is_error=True,
        )

    parsed = _parse_buscar_filters(cmd.args)
    if isinstance(parsed, str):
        return HandlerResult(text=parsed, is_error=True)

    if parsed.topico is not None and parsed.topico not in DEFAULT_TOPIC_IDS:
        extra_topics = await ctx.storage.get_extra_topics()
        valid_extra = extra_topics.topic_ids() if extra_topics is not None else set()
        if parsed.topico not in valid_extra:
            return HandlerResult(
                text=(
                    f"❌ Tópico inválido: `{parsed.topico}`. "
                    "Use `/topicos listar` para ver os tópicos disponíveis."
                ),
                is_error=True,
            )

    has_filter = any([parsed.uf, parsed.ano, parsed.topico, parsed.tipo, parsed.severidade])
    if not parsed.termos and not has_filter:
        return HandlerResult(
            text="❌ Forneça pelo menos um termo de busca ou um filtro.", is_error=True
        )

    since: datetime | None = None
    until: datetime | None = None
    if parsed.ano is not None:
        since = datetime(parsed.ano, 1, 1, tzinfo=UTC)
        until = datetime(parsed.ano + 1, 1, 1, tzinfo=UTC)

    docs = await ctx.storage.search_documentos(
        terms=parsed.termos,
        uf=parsed.uf,
        since=since,
        limit=_BUSCAR_SCAN_LIMIT,
        scan_limit=_BUSCAR_SCAN_LIMIT,
    )

    matched = []
    for d in docs:
        if until is not None and d.original.fetched_at and d.original.fetched_at >= until:
            continue
        if parsed.topico is not None and (d.llm is None or parsed.topico not in d.llm.topics):
            continue
        if parsed.tipo is not None and (d.llm is None or d.llm.tipo != parsed.tipo):
            continue
        if parsed.severidade is not None and (
            d.llm is None or d.llm.severity_tier != parsed.severidade
        ):
            continue
        if not _matches_text(parsed.termos, d):
            continue
        matched.append(d)

    matched.sort(
        key=lambda d: (
            -(d.llm.relevancia if d.llm is not None else 0),
            -(d.original.fetched_at.timestamp() if d.original.fetched_at else 0),
        )
    )
    truncated = len(matched) > parsed.limite
    matched = matched[: parsed.limite]

    # Cabeçalho (já em MarkdownV2 escapado)
    filtros_str_parts: list[str] = []
    if parsed.termos:
        filtros_str_parts.append(escape_markdown_v2(" ".join(parsed.termos)))
    if parsed.uf:
        filtros_str_parts.append(f"uf\\={escape_markdown_v2(parsed.uf)}")
    if parsed.ano:
        filtros_str_parts.append(f"ano\\={parsed.ano}")
    if parsed.topico:
        filtros_str_parts.append(f"topico\\={escape_markdown_v2(parsed.topico)}")
    if parsed.tipo:
        filtros_str_parts.append(f"tipo\\={escape_markdown_v2(parsed.tipo.value)}")
    if parsed.severidade:
        filtros_str_parts.append(f"severidade\\={escape_markdown_v2(parsed.severidade.value)}")
    filtros_str = " · ".join(filtros_str_parts)

    if not matched:
        return HandlerResult(
            text=f"🔍 Nenhum resultado para: {filtros_str}", is_error=False, pre_escaped=True
        )

    total_str = f"{len(matched)}\\+" if truncated else str(len(matched))
    header = f"*🔍 {total_str} resultado\\(s\\)* — {filtros_str}"
    cards = [_format_buscar_card(d) for d in matched]
    text = header + "\n\n" + "\n\n".join(cards)
    if truncated:
        text += (
            f"\n\n_Mostrando os primeiros {parsed.limite}\\. "
            f"Use `limite\\=N` \\(máx {_BUSCAR_MAX_LIMIT}\\) ou refine os filtros\\._"
        )
    return HandlerResult(text=text, pre_escaped=True)


_TOPIC_DEFAULT_DESCRICOES = {
    "itcd": "Imposto sobre Transmissão Causa Mortis e Doação (ITCD/ITCMD/ITD)",
    "sucessoes": "Direito Civil das Sucessões (CC 1.784+): herança, testamento, inventário",
    "regime_bens": "Regime de Bens (CC 1.639-1.688): comunhão, separação, pacto antenupcial",
}

_TOPIC_ID_REGEX = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


async def _topicos_listar(ctx: BotContext) -> HandlerResult:
    cfg = await ctx.storage.get_extra_topics()
    extras = cfg.topics if cfg is not None else []
    lines = ["🗂️ *Divisões temáticas*", ""]
    lines.append("*Defaults*:")
    for tid, desc in _TOPIC_DEFAULT_DESCRICOES.items():
        lines.append(f"• `{tid}` — {desc}")
    lines.append("")
    if extras:
        lines.append(f"*Extras dinâmicos* ({len(extras)}):")
        lines.extend(
            f"• `{entry.id}` — {entry.descricao}" for entry in sorted(extras, key=lambda e: e.id)
        )
    else:
        lines.append("*Extras dinâmicos*: nenhum.")
    lines.append("")
    lines.append("Use `/topicos adicionar <id> <descrição>` para criar novo tópico.")
    lines.append("Use `/buscar <termo> topico=<id>` para filtrar resultados.")
    return HandlerResult(text="\n".join(lines))


async def _topicos_adicionar(  # noqa: PLR0911
    ctx: BotContext, cmd: ParsedCommand
) -> HandlerResult:
    # Args: ["adicionar", <id>, <palavras_descricao...>]
    if len(cmd.args) < MIN_ARGS_WITH_UF + 1:
        return HandlerResult(
            text="❌ Uso: `/topicos adicionar <id> <descrição em palavras>`",
            is_error=True,
        )
    topic_id = cmd.args[1].lower().strip()
    descricao = " ".join(cmd.args[2:]).strip()

    if not _TOPIC_ID_REGEX.fullmatch(topic_id):
        return HandlerResult(
            text=(
                f"❌ ID inválido: `{topic_id}`. Use letras minúsculas, dígitos e `_`, "
                "começando por letra."
            ),
            is_error=True,
        )
    if topic_id in DEFAULT_TOPIC_IDS:
        return HandlerResult(
            text=f"❌ `{topic_id}` é um tópico padrão e não pode ser duplicado.",
            is_error=True,
        )
    if (
        len(descricao) < limits.MIN_TOPIC_DESCRIPTION_LENGTH
        or len(descricao) > limits.MAX_TOPIC_DESCRIPTION_LENGTH
    ):
        return HandlerResult(
            text=(
                f"❌ Descrição deve ter entre {limits.MIN_TOPIC_DESCRIPTION_LENGTH} "
                f"e {limits.MAX_TOPIC_DESCRIPTION_LENGTH} chars (LLM precisa entender)."
            ),
            is_error=True,
        )

    cfg = await ctx.storage.get_extra_topics()
    if cfg is None:
        cfg = ExtraTopicsConfig(
            owner_id=ctx.settings.OWNER_ID,
            topics=[],
            updated_at=datetime.now(UTC),
            updated_by="bot",
        )
    if any(t.id == topic_id for t in cfg.topics):
        return HandlerResult(
            text=f"⚠️ Tópico `{topic_id}` já existe nos extras.",
        )
    if len(cfg.topics) >= limits.MAX_EXTRA_TOPICS:
        return HandlerResult(
            text=(
                f"❌ Limite de {limits.MAX_EXTRA_TOPICS} tópicos extras atingido. "
                "Remova algum com `/topicos remover` antes."
            ),
            is_error=True,
        )

    new_entry = TopicEntry(
        id=topic_id,
        descricao=descricao,
        criado_em=datetime.now(UTC),
        criado_por="bot",
    )
    new_cfg = cfg.model_copy(
        update={
            "topics": [*cfg.topics, new_entry],
            "updated_at": datetime.now(UTC),
            "updated_by": "bot",
        }
    )
    try:
        await ctx.storage.save_extra_topics(new_cfg)
    except (ValueError, RuntimeError) as e:  # pragma: no cover - proteção defensiva
        return HandlerResult(text=f"❌ Falha ao persistir: {e}", is_error=True)
    await log_bot_action(
        ctx, action="bot.topicos.adicionar", payload={"id": topic_id, "descricao": descricao}
    )
    return HandlerResult(
        text=(
            f"✅ Tópico `{topic_id}` adicionado. Total: {len(new_cfg.topics)} extras. "
            "LLM passará a classificar próximas coletas nesta categoria."
        )
    )


async def _topicos_remover(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if len(cmd.args) < MIN_ARGS_WITH_UF:
        return HandlerResult(text="❌ Uso: `/topicos remover <id>`", is_error=True)
    topic_id = cmd.args[1].lower().strip()
    if topic_id in DEFAULT_TOPIC_IDS:
        return HandlerResult(
            text=f"❌ `{topic_id}` é tópico padrão e não pode ser removido.",
            is_error=True,
        )

    cfg = await ctx.storage.get_extra_topics()
    if cfg is None or not any(t.id == topic_id for t in cfg.topics):
        return HandlerResult(text=f"⚠️ Tópico `{topic_id}` não encontrado nos extras.")

    new_topics = [t for t in cfg.topics if t.id != topic_id]
    new_cfg = cfg.model_copy(
        update={
            "topics": new_topics,
            "updated_at": datetime.now(UTC),
            "updated_by": "bot",
        }
    )
    try:
        await ctx.storage.save_extra_topics(new_cfg)
    except (ValueError, RuntimeError) as e:  # pragma: no cover - proteção defensiva
        return HandlerResult(text=f"❌ Falha ao persistir: {e}", is_error=True)
    await log_bot_action(ctx, action="bot.topicos.remover", payload={"id": topic_id})
    return HandlerResult(
        text=(
            f"✅ Tópico `{topic_id}` removido. Documentos antigos classificados "
            "neste tópico continuam pesquisáveis (não migra automaticamente)."
        )
    )


_TOPICOS_SUBHANDLERS = {
    "listar": lambda ctx, _cmd: _topicos_listar(ctx),
    "adicionar": _topicos_adicionar,
    "remover": _topicos_remover,
}


async def handle_topicos(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    """Gerencia tópicos dinâmicos (B2): listar | adicionar | remover.

    Sem args, ou subcomando inválido, devolve uso. Para listagem rápida
    inline, basta `/topicos listar`.
    """
    if not cmd.args:
        # Compat: chamado puro mostra a listagem (UX preservada).
        return await _topicos_listar(ctx)
    sub = cmd.args[0].lower()
    handler = _TOPICOS_SUBHANDLERS.get(sub)
    if handler is None:
        return HandlerResult(text=f"❌ Subcomando desconhecido: '{sub}'", is_error=True)
    return await handler(ctx, cmd)


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
    lines.extend(
        f"• [{w.watch_id[:8]}] '{w.pattern}' ({w.pattern_type}, rel≥{w.relevancia_min})"
        for w in watches[:20]
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

    Renderiza os documentos classificados do período com o mesmo template
    Telegram do digest automático, incluindo `resumo_completo` quando existe.
    Documentos pendentes continuam contabilizados no cabeçalho.
    """
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    if len(cmd.args) > 1:
        return HandlerResult(
            text="❌ Uso: /relatorio [diario|semanal]",
            is_error=True,
        )

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

    label = "Diário" if periodo == "diario" else "Semanal"
    classified = sorted(
        (d for d in docs if d.llm is not None),
        key=lambda d: d.llm.relevancia if d.llm else 0,
        reverse=True,
    )
    pendentes = len(docs) - len(classified)
    if not classified:
        return HandlerResult(
            text=f"📊 Relatório {label}: {len(docs)} documento(s), todos pendentes de LLM.",
        )

    rendered = render_telegram(
        classified,
        digest_label=f"Relatório {label}",
        data_geracao=datetime.now(UTC),
    )
    if pendentes:
        rendered += (
            "\n\n_"
            f"{pendentes} documento\\(s\\) pendente\\(s\\) de classificação LLM "
            "ficaram fora do detalhamento\\."
            "_"
        )
    return HandlerResult(text=rendered, pre_escaped=True)


# ─────────────────────────────────────────────────────────────────────────────
# /temas — gerencia keywords extras dinâmicas (Conceito 1 do design B2)
# ─────────────────────────────────────────────────────────────────────────────

_TEMAS_TOPIC_REGEX = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TEMAS_DEFAULT_TOPIC = "geral"


def _parse_temas_args(args: list[str]) -> tuple[str, str | None]:
    """Separa termo livre dos filtros `topico=`. Retorna (termo, topico|None)."""
    topic: str | None = None
    parts: list[str] = []
    for arg in args:
        if arg.startswith("topico="):
            topic = arg.split("=", 1)[1].strip().lower()
        else:
            parts.append(arg)
    return " ".join(parts).strip(), topic


async def _temas_listar(ctx: BotContext) -> HandlerResult:
    cfg = await ctx.storage.get_extra_keywords()
    base = f"🗂 *Defaults*: {len(KEYWORDS_DEFAULT)} termos (união itcd+sucessoes+regime\\_bens)"
    if cfg is None or cfg.total_count() == 0:
        return HandlerResult(
            text=(
                f"{base}\n\n"
                "📋 *Extras*: nenhuma adicionada\\.\n"
                "Use `/temas adicionar <termo> [topico=...]` para ampliar\\."
            ),
            pre_escaped=True,
        )
    lines = [base, ""]
    for topic in sorted(cfg.keywords_by_topic):
        kws = cfg.keywords_by_topic[topic]
        if not kws:
            continue
        topic_esc = escape_markdown_v2(topic)
        lines.append(f"🔹 *{topic_esc}* \\(\\+{len(kws)} extras\\)")
        lines.extend(f"  • {escape_markdown_v2(kw)}" for kw in sorted(kws))
        lines.append("")
    lines.append(f"_Total de extras: {cfg.total_count()}\\._")
    return HandlerResult(text="\n".join(lines), pre_escaped=True)


async def _temas_adicionar(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:  # noqa: PLR0911
    if len(cmd.args) < MIN_ARGS_WITH_UF:
        return HandlerResult(
            text=(
                "❌ Uso: `/temas adicionar <termo> [topico=itcd|sucessoes|regime_bens|geral|...]`"
            ),
            is_error=True,
        )
    termo, topic = _parse_temas_args(cmd.args[1:])
    if not termo:
        return HandlerResult(text="❌ Forneça o termo após `/temas adicionar`.", is_error=True)
    if topic is None:
        topic = _TEMAS_DEFAULT_TOPIC
    if not _TEMAS_TOPIC_REGEX.fullmatch(topic):
        return HandlerResult(
            text=f"❌ Tópico inválido: `{topic}`. Use letras minúsculas, dígitos e `_`.",
            is_error=True,
        )
    if len(termo) < limits.MIN_EXTRA_KEYWORD_LENGTH or len(termo) > limits.MAX_EXTRA_KEYWORD_LENGTH:
        return HandlerResult(
            text=(
                f"❌ Termo deve ter entre {limits.MIN_EXTRA_KEYWORD_LENGTH} "
                f"e {limits.MAX_EXTRA_KEYWORD_LENGTH} chars."
            ),
            is_error=True,
        )

    cfg = await ctx.storage.get_extra_keywords()
    if cfg is None:
        cfg = ExtraKeywordsConfig(
            owner_id=ctx.settings.OWNER_ID,
            keywords_by_topic={},
            updated_at=datetime.now(UTC),
            updated_by="bot",
        )

    if cfg.total_count() >= limits.MAX_EXTRA_KEYWORDS_TOTAL:
        return HandlerResult(
            text=(
                f"❌ Limite de {limits.MAX_EXTRA_KEYWORDS_TOTAL} keywords extras atingido. "
                "Remova alguma com `/temas remover` antes."
            ),
            is_error=True,
        )

    termo_lower_set = {kw.lower() for kws in cfg.keywords_by_topic.values() for kw in kws}
    if termo.lower() in {kw.lower() for kw in KEYWORDS_DEFAULT}:
        return HandlerResult(
            text=f"⚠️ Termo `{termo}` já existe nos defaults — não precisa adicionar.",
        )
    if termo.lower() in termo_lower_set:
        return HandlerResult(text=f"⚠️ Termo `{termo}` já está nos extras.")

    new_by_topic = {t: list(kws) for t, kws in cfg.keywords_by_topic.items()}
    new_by_topic.setdefault(topic, []).append(termo)
    new_cfg = cfg.model_copy(
        update={
            "keywords_by_topic": new_by_topic,
            "updated_at": datetime.now(UTC),
            "updated_by": "bot",
        }
    )
    try:
        await ctx.storage.save_extra_keywords(new_cfg)
    except (ValueError, RuntimeError) as e:  # pragma: no cover - proteção defensiva
        return HandlerResult(text=f"❌ Falha ao persistir: {e}", is_error=True)
    await log_bot_action(
        ctx, action="bot.temas.adicionar", payload={"termo": termo, "topico": topic}
    )
    return HandlerResult(
        text=(
            f"✅ Keyword `{termo}` adicionada ao tópico `{topic}`. "
            f"Total extras: {new_cfg.total_count()}."
        )
    )


async def _temas_remover(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    if len(cmd.args) < MIN_ARGS_WITH_UF:
        return HandlerResult(text="❌ Uso: `/temas remover <termo> [topico=...]`", is_error=True)
    termo, topic = _parse_temas_args(cmd.args[1:])
    if not termo:
        return HandlerResult(text="❌ Forneça o termo a remover.", is_error=True)

    cfg = await ctx.storage.get_extra_keywords()
    if cfg is None or cfg.total_count() == 0:
        return HandlerResult(text="⚠️ Nenhuma keyword extra configurada.")

    new_by_topic: dict[str, list[str]] = {}
    removed_from: list[str] = []
    for t, kws in cfg.keywords_by_topic.items():
        if topic is not None and t != topic:
            new_by_topic[t] = list(kws)
            continue
        if any(kw.lower() == termo.lower() for kw in kws):
            new_by_topic[t] = [kw for kw in kws if kw.lower() != termo.lower()]
            removed_from.append(t)
        else:
            new_by_topic[t] = list(kws)
    if not removed_from:
        suffix = f" no tópico `{topic}`" if topic else ""
        return HandlerResult(text=f"⚠️ Termo `{termo}` não encontrado nos extras{suffix}.")

    new_cfg = cfg.model_copy(
        update={
            "keywords_by_topic": new_by_topic,
            "updated_at": datetime.now(UTC),
            "updated_by": "bot",
        }
    )
    try:
        await ctx.storage.save_extra_keywords(new_cfg)
    except (ValueError, RuntimeError) as e:  # pragma: no cover - proteção defensiva
        return HandlerResult(text=f"❌ Falha ao persistir: {e}", is_error=True)
    await log_bot_action(
        ctx,
        action="bot.temas.remover",
        payload={"termo": termo, "removed_from": removed_from},
    )
    topics_csv = ", ".join(sorted(removed_from))
    return HandlerResult(
        text=f"✅ `{termo}` removido de {len(removed_from)} tópico(s): {topics_csv}."
    )


async def _temas_reset(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    _, topic = _parse_temas_args(cmd.args[1:])

    cfg = await ctx.storage.get_extra_keywords()
    if cfg is None or cfg.total_count() == 0:
        return HandlerResult(text="⚠️ Nenhuma keyword extra para remover.")

    if topic is None:
        total = cfg.total_count()
        new_cfg = cfg.model_copy(
            update={
                "keywords_by_topic": {},
                "updated_at": datetime.now(UTC),
                "updated_by": "bot",
            }
        )
        try:
            await ctx.storage.save_extra_keywords(new_cfg)
        except (ValueError, RuntimeError) as e:  # pragma: no cover - proteção defensiva
            return HandlerResult(text=f"❌ Falha ao persistir: {e}", is_error=True)
        await log_bot_action(ctx, action="bot.temas.reset", payload={"all": True, "count": total})
        return HandlerResult(text=f"✅ Todas as {total} keywords extras removidas.")

    if topic not in cfg.keywords_by_topic or not cfg.keywords_by_topic[topic]:
        return HandlerResult(text=f"⚠️ Tópico `{topic}` não tem keywords extras.")

    count = len(cfg.keywords_by_topic[topic])
    new_by_topic = {t: list(kws) for t, kws in cfg.keywords_by_topic.items() if t != topic}
    new_cfg = cfg.model_copy(
        update={
            "keywords_by_topic": new_by_topic,
            "updated_at": datetime.now(UTC),
            "updated_by": "bot",
        }
    )
    try:
        await ctx.storage.save_extra_keywords(new_cfg)
    except (ValueError, RuntimeError) as e:  # pragma: no cover - proteção defensiva
        return HandlerResult(text=f"❌ Falha ao persistir: {e}", is_error=True)
    await log_bot_action(ctx, action="bot.temas.reset", payload={"topico": topic, "count": count})
    return HandlerResult(text=f"✅ {count} keyword(s) extras do tópico `{topic}` removidas.")


_TEMAS_SUBHANDLERS = {
    "listar": lambda ctx, _cmd: _temas_listar(ctx),
    "adicionar": _temas_adicionar,
    "remover": _temas_remover,
    "reset": _temas_reset,
}


async def handle_temas(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    """Gerencia keywords extras dinâmicas — listar | adicionar | remover | reset."""
    if not cmd.args:
        return HandlerResult(
            text="❌ Uso: `/temas <listar|adicionar|remover|reset> [args]`", is_error=True
        )
    sub = cmd.args[0].lower()
    handler = _TEMAS_SUBHANDLERS.get(sub)
    if handler is None:
        return HandlerResult(text=f"❌ Subcomando desconhecido: '{sub}'", is_error=True)
    return await handler(ctx, cmd)


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
    "temas": handle_temas,
}


def _register_extra_handlers() -> None:
    """Registra handlers adicionais (Categoria 6 IDEAS.md).

    Importação tardia para evitar ciclo handlers_extra ↔ handlers.
    """
    from monitoritcd.bot.handlers_extra import EXTRA_HANDLERS  # noqa: PLC0415

    HANDLERS.update(EXTRA_HANDLERS)


_register_extra_handlers()


async def dispatch(ctx: BotContext, cmd: ParsedCommand) -> HandlerResult:
    """Dispatch para handler correspondente. Retorna erro se desconhecido."""
    handler = HANDLERS.get(cmd.name)
    if handler is None:
        return HandlerResult(text=f"❌ Comando desconhecido: /{cmd.name}", is_error=True)
    return await handler(ctx, cmd)
