"""Testes de integração dos handlers do bot.

Cada handler é testado com `BotContext` real (InMemoryStorage) e
`ParsedCommand` construído manualmente.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from monitoritcd.bot.auth import TwoStepConfirmation
from monitoritcd.bot.handlers import (
    BotContext,
    ParsedCommand,
    dispatch,
    handle_buscar,
    handle_confirmar,
    handle_estados,
    handle_help,
    handle_marcar,
    handle_observar,
    handle_relatorio,
    handle_start,
    handle_status,
    handle_topicos,
)
from monitoritcd.core.config import Settings
from monitoritcd.core.models import (
    ActiveStatesConfig,
    Documento,
    LLMResult,
    Parser,
    RawItem,
    SeverityTier,
    Source,
    StatusDocumento,
    TipoAto,
    TipoFonte,
)
from monitoritcd.storage import InMemoryStorage

NOW = datetime(2026, 4, 24, tzinfo=UTC)
OWNER = "owner"


def _settings() -> Settings:
    return Settings(
        OWNER_ID=OWNER,
        OWNER_EMAIL="o@example.com",
        GEMINI_API_KEY=SecretStr("g"),
        GMAIL_USER="b@example.com",
        GMAIL_APP_PASSWORD=SecretStr("p"),
        TELEGRAM_BOT_TOKEN=SecretStr("t"),
        TELEGRAM_OWNER_CHAT_ID=1,
        TELEGRAM_WEBHOOK_SECRET=SecretStr("ws"),
        FIREBASE_PROJECT_ID="p",
        FIREBASE_STORAGE_BUCKET="p.appspot.com",
        FIREBASE_SERVICE_ACCOUNT_JSON=SecretStr("{}"),
    )


async def _ctx() -> BotContext:
    return BotContext(
        settings=_settings(),
        storage=InMemoryStorage(OWNER),
        confirmation=TwoStepConfirmation(),
    )


def _doc(*, doc_id: str = "d1", titulo: str = "PL ITCMD SP", uf: str = "SP") -> Documento:
    raw = RawItem(
        source_id="s",
        titulo_raw=titulo,
        url="https://x.gov.br/",
        fetched_at=NOW,
        content_hash="a" * 64,
    )
    src = Source(
        id="s",
        uf=uf,
        nome="x",
        tipo=TipoFonte.SEFAZ,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = LLMResult(
        classified_at=NOW,
        llm_model="x",
        llm_prompt_version="v1",
        tipo=TipoAto.PROJETO_LEI,
        relevancia=8,
        severity_tier=SeverityTier.ALTA,
        resumo="Resumo",
    )
    return Documento(
        owner_id=OWNER,
        doc_id=doc_id,
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )


@pytest.mark.integration
class TestStart:
    @pytest.mark.asyncio
    async def test_start_returns_help(self) -> None:
        ctx = await _ctx()
        result = await handle_start(ctx, ParsedCommand(name="start", args=[]))
        assert "MonitorITCD" in result.text
        assert "/help" in result.text


@pytest.mark.integration
class TestStatus:
    @pytest.mark.asyncio
    async def test_status_empty(self) -> None:
        ctx = await _ctx()
        result = await handle_status(ctx, ParsedCommand(name="status", args=[]))
        assert "0 total" in result.text or "Documentos: 0" in result.text

    @pytest.mark.asyncio
    async def test_status_with_docs(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc())
        result = await handle_status(ctx, ParsedCommand(name="status", args=[]))
        assert "1 total" in result.text or "Documentos: 1" in result.text


@pytest.mark.integration
class TestBuscar:
    @pytest.mark.asyncio
    async def test_busca_sem_termo(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=[]))
        assert result.is_error
        assert "Uso" in result.text

    @pytest.mark.asyncio
    async def test_busca_no_match(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc())
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["zzznada"]))
        assert "Nenhum" in result.text

    @pytest.mark.asyncio
    async def test_busca_match_titulo(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="PL 1234/2026 — ITCMD SP"))
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["1234"]))
        assert "1234" in result.text


@pytest.mark.integration
class TestEstados:
    @pytest.mark.asyncio
    async def test_estados_sem_args(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(ctx, ParsedCommand(name="estados", args=[]))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_estados_listar_vazio(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(ctx, ParsedCommand(name="estados", args=["listar"]))
        assert "Nenhuma" in result.text

    @pytest.mark.asyncio
    async def test_estados_listar_com_ufs(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_active_states(
            ActiveStatesConfig(
                owner_id=OWNER,
                active_uf=["SP", "RJ"],
                updated_at=NOW,
                updated_by="bot",
            ),
        )
        result = await handle_estados(ctx, ParsedCommand(name="estados", args=["listar"]))
        assert "SP" in result.text
        assert "RJ" in result.text

    @pytest.mark.asyncio
    async def test_estados_ativar_uf_invalida(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(
            ctx,
            ParsedCommand(name="estados", args=["ativar", "xx"]),
        )
        assert result.is_error

    @pytest.mark.asyncio
    async def test_estados_ativar_uf_valida(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(
            ctx,
            ParsedCommand(name="estados", args=["ativar", "SP"]),
        )
        assert "SP" in result.text
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_estados_desativar_emite_token(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(
            ctx,
            ParsedCommand(name="estados", args=["desativar", "SP"]),
        )
        assert "/confirmar" in result.text
        assert "60s" in result.text or "60 s" in result.text

    @pytest.mark.asyncio
    async def test_estados_subcomando_desconhecido(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(
            ctx,
            ParsedCommand(name="estados", args=["xyz"]),
        )
        assert result.is_error

    @pytest.mark.asyncio
    async def test_estados_ativar_sem_uf(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(
            ctx,
            ParsedCommand(name="estados", args=["ativar"]),
        )
        assert result.is_error

    @pytest.mark.asyncio
    async def test_estados_desativar_sem_uf(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(
            ctx,
            ParsedCommand(name="estados", args=["desativar"]),
        )
        assert result.is_error

    @pytest.mark.asyncio
    async def test_estados_desativar_uf_invalida(self) -> None:
        ctx = await _ctx()
        result = await handle_estados(
            ctx,
            ParsedCommand(name="estados", args=["desativar", "zz"]),
        )
        assert result.is_error


@pytest.mark.integration
class TestConfirmar:
    @pytest.mark.asyncio
    async def test_confirmar_token_valido(self) -> None:
        ctx = await _ctx()
        # Emite token primeiro
        await handle_estados(ctx, ParsedCommand(name="estados", args=["desativar", "SP"]))
        # Pega o token emitido
        tokens_dict = ctx.confirmation._tokens
        assert tokens_dict
        token = next(iter(tokens_dict.keys()))

        result = await handle_confirmar(ctx, ParsedCommand(name="confirmar", args=[token]))
        assert "confirmada" in result.text.lower()

    @pytest.mark.asyncio
    async def test_confirmar_sem_args(self) -> None:
        ctx = await _ctx()
        result = await handle_confirmar(ctx, ParsedCommand(name="confirmar", args=[]))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_confirmar_token_invalido(self) -> None:
        ctx = await _ctx()
        result = await handle_confirmar(
            ctx,
            ParsedCommand(name="confirmar", args=["fake-token"]),
        )
        assert result.is_error


@pytest.mark.integration
class TestTopicos:
    @pytest.mark.asyncio
    async def test_topicos_lists_three_divisions(self) -> None:
        ctx = await _ctx()
        result = await handle_topicos(ctx, ParsedCommand(name="topicos", args=[]))
        assert "itcd" in result.text
        assert "sucessoes" in result.text
        assert "regime_bens" in result.text


@pytest.mark.integration
class TestBuscarComTopico:
    @pytest.mark.asyncio
    async def test_busca_com_filtro_topico_invalido(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(
            ctx,
            ParsedCommand(name="buscar", args=["itcmd", "topico=foo"]),
        )
        assert result.is_error
        assert "Tópico inválido" in result.text

    @pytest.mark.asyncio
    async def test_busca_so_com_filtro_topico_funciona(self) -> None:
        # Antes: erro. Depois: aceita filtros sozinhos (sem termos livres).
        # Quando não há docs, retorna "Nenhum resultado".
        ctx = await _ctx()
        result = await handle_buscar(
            ctx,
            ParsedCommand(name="buscar", args=["topico=itcd"]),
        )
        assert not result.is_error
        assert "Nenhum resultado" in result.text


@pytest.mark.integration
class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_known_command(self) -> None:
        ctx = await _ctx()
        result = await dispatch(ctx, ParsedCommand(name="status", args=[]))
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_dispatch_unknown_returns_error(self) -> None:
        ctx = await _ctx()
        result = await dispatch(ctx, ParsedCommand(name="naoexiste", args=[]))
        assert result.is_error


@pytest.mark.integration
class TestHelp:
    """`/help` reaproveita `handle_start` (linha 124 do handlers.py)."""

    @pytest.mark.asyncio
    async def test_help_returns_start_text(self) -> None:
        ctx = await _ctx()
        result_help = await handle_help(ctx, ParsedCommand(name="help", args=[]))
        result_start = await handle_start(ctx, ParsedCommand(name="start", args=[]))
        assert result_help.text == result_start.text


@pytest.mark.integration
class TestObservar:
    """Edge cases dos sub-handlers de /observar."""

    @pytest.mark.asyncio
    async def test_observar_sem_args_emite_uso(self) -> None:
        ctx = await _ctx()
        result = await handle_observar(ctx, ParsedCommand(name="observar", args=[]))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_observar_remover_sem_id_emite_uso(self) -> None:
        ctx = await _ctx()
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["remover"]),
        )
        assert result.is_error
        assert "Uso:" in result.text

    @pytest.mark.asyncio
    async def test_observar_listar_vazio(self) -> None:
        ctx = await _ctx()
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["listar"]),
        )
        assert "Nenhum watch ativo" in result.text

    @pytest.mark.asyncio
    async def test_observar_adicionar_e_remover(self) -> None:
        ctx = await _ctx()
        # Cria
        added = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["x", "holding", "familiar"]),
        )
        assert "Watch criado" in added.text
        # Lista mostra
        listed = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["listar"]),
        )
        assert "holding familiar" in listed.text
        # Remove pelo prefixo do id
        watches = await ctx.storage.list_watches()
        prefix = watches[0].watch_id[:6]
        removed = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["remover", prefix]),
        )
        assert "Watch removido" in removed.text

    @pytest.mark.asyncio
    async def test_observar_remover_id_inexistente(self) -> None:
        ctx = await _ctx()
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["remover", "ghost123"]),
        )
        assert result.is_error
        assert "não encontrado" in result.text

    @pytest.mark.asyncio
    async def test_observar_remover_prefixo_ambiguo(self) -> None:
        # Cria 2 watches; usa prefixo curto que casa em ambos -> erro de ambiguidade
        ctx = await _ctx()
        from uuid import uuid4  # noqa: PLC0415

        from monitoritcd.core.models import Watch  # noqa: PLC0415

        # Forca dois watch_ids com mesmo prefixo "abcd"
        for pattern in ("primeiro", "segundo"):
            await ctx.storage.save_watch(
                Watch(
                    owner_id=OWNER,
                    watch_id="abcd" + uuid4().hex[:12],
                    pattern=pattern,
                    pattern_type="term",
                    relevancia_min=5,
                    cooldown_hours=24,
                    created_at=NOW,
                ),
            )

        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["remover", "abcd"]),
        )
        assert result.is_error
        assert "Ambíguo" in result.text

    @pytest.mark.asyncio
    async def test_observar_termo_curto_rejeitado(self) -> None:
        # handle_observar prepende "adicionar" -> _watch_adicionar recebe
        # args=["adicionar", "ab"] e faz join(args[1:]) = "ab" (2 chars < 3)
        ctx = await _ctx()
        result = await handle_observar(
            ctx,
            ParsedCommand(name="observar", args=["ab"]),
        )
        assert result.is_error
        assert "muito curto" in result.text


@pytest.mark.integration
class TestMarcar:
    """`/marcar <doc_id_prefix> <tag>` adiciona user_tag ao documento."""

    @pytest.mark.asyncio
    async def test_marcar_sem_args_emite_uso(self) -> None:
        ctx = await _ctx()
        result = await handle_marcar(ctx, ParsedCommand(name="marcar", args=[]))
        assert result.is_error
        assert "Uso:" in result.text

    @pytest.mark.asyncio
    async def test_marcar_apenas_doc_id_emite_uso(self) -> None:
        ctx = await _ctx()
        result = await handle_marcar(ctx, ParsedCommand(name="marcar", args=["abc"]))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_marcar_doc_inexistente(self) -> None:
        ctx = await _ctx()
        result = await handle_marcar(
            ctx,
            ParsedCommand(name="marcar", args=["ghost", "minhatag"]),
        )
        assert result.is_error
        assert "não encontrado" in result.text

    @pytest.mark.asyncio
    async def test_marcar_doc_existente_adiciona_tag(self) -> None:
        ctx = await _ctx()
        doc = _doc()
        await ctx.storage.save_documento(doc)
        result = await handle_marcar(
            ctx,
            ParsedCommand(name="marcar", args=[doc.doc_id[:6], "prioridade-alta"]),
        )
        assert not result.is_error
        assert "prioridade-alta" in result.text
        # Tag persistida
        loaded = await ctx.storage.get_documento(doc.doc_id)
        assert loaded is not None
        assert "prioridade-alta" in loaded.user_tags

    @pytest.mark.asyncio
    async def test_marcar_idempotente(self) -> None:
        ctx = await _ctx()
        doc = _doc()
        await ctx.storage.save_documento(doc)
        await handle_marcar(
            ctx,
            ParsedCommand(name="marcar", args=[doc.doc_id[:6], "tag1"]),
        )
        await handle_marcar(
            ctx,
            ParsedCommand(name="marcar", args=[doc.doc_id[:6], "tag1"]),
        )
        loaded = await ctx.storage.get_documento(doc.doc_id)
        assert loaded is not None
        assert loaded.user_tags.count("tag1") == 1

    @pytest.mark.asyncio
    async def test_marcar_prefixo_ambiguo(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(doc_id="abcd111"))
        await ctx.storage.save_documento(_doc(doc_id="abcd222"))
        result = await handle_marcar(
            ctx,
            ParsedCommand(name="marcar", args=["abcd", "x"]),
        )
        assert result.is_error
        assert "Ambíguo" in result.text

    @pytest.mark.asyncio
    async def test_marcar_tag_vazia(self) -> None:
        ctx = await _ctx()
        doc = _doc()
        await ctx.storage.save_documento(doc)
        result = await handle_marcar(
            ctx,
            ParsedCommand(name="marcar", args=[doc.doc_id[:6], "   "]),
        )
        assert result.is_error
        assert "vazia" in result.text


@pytest.mark.integration
class TestRelatorio:
    """`/relatorio [diario|semanal]` resume documentos do período."""

    @pytest.mark.asyncio
    async def test_periodo_invalido(self) -> None:
        ctx = await _ctx()
        result = await handle_relatorio(
            ctx,
            ParsedCommand(name="relatorio", args=["mensal"]),
        )
        assert result.is_error
        assert "inválido" in result.text

    @pytest.mark.asyncio
    async def test_diario_vazio(self) -> None:
        ctx = await _ctx()
        result = await handle_relatorio(
            ctx,
            ParsedCommand(name="relatorio", args=[]),
        )
        assert "Nenhum documento" in result.text

    @pytest.mark.asyncio
    async def test_diario_com_docs(self) -> None:
        # Doc com fetched_at recente para passar no filter `since=now()-1d`
        from datetime import UTC, datetime  # noqa: PLC0415

        from monitoritcd.core.models import RawItem  # noqa: PLC0415

        ctx = await _ctx()
        recent_raw = RawItem(
            source_id="s",
            titulo_raw="PL recente",
            url="https://x.gov.br/r",
            fetched_at=datetime.now(UTC),
            content_hash="b" * 64,
        )
        recent_doc = _doc().model_copy(update={"original": recent_raw})
        await ctx.storage.save_documento(recent_doc)
        result = await handle_relatorio(
            ctx,
            ParsedCommand(name="relatorio", args=["diario"]),
        )
        assert "Diário" in result.text or "Relatório" in result.text

    @pytest.mark.asyncio
    async def test_semanal_com_docs(self) -> None:
        # Mesma estratégia: fetched_at recente
        from datetime import UTC, datetime  # noqa: PLC0415

        from monitoritcd.core.models import RawItem  # noqa: PLC0415

        ctx = await _ctx()
        recent_raw = RawItem(
            source_id="s",
            titulo_raw="PL recente",
            url="https://x.gov.br/r",
            fetched_at=datetime.now(UTC),
            content_hash="c" * 64,
        )
        recent_doc = _doc().model_copy(update={"original": recent_raw})
        await ctx.storage.save_documento(recent_doc)
        result = await handle_relatorio(
            ctx,
            ParsedCommand(name="relatorio", args=["semanal"]),
        )
        assert "Semanal" in result.text

    @pytest.mark.asyncio
    async def test_relatorio_doc_sem_llm_aparece_no_total_mas_nao_em_tier(self) -> None:
        # Cobre branch 486->485: doc sem llm é contado no total mas pulado
        # no tier_counts e top-rated.
        from datetime import UTC, datetime  # noqa: PLC0415

        from monitoritcd.core.models import RawItem  # noqa: PLC0415

        ctx = await _ctx()
        raw = RawItem(
            source_id="s",
            titulo_raw="Sem LLM",
            url="https://x.gov.br/sl",
            fetched_at=datetime.now(UTC),
            content_hash="d" * 64,
        )
        doc_sem_llm = _doc().model_copy(update={"original": raw, "llm": None})
        await ctx.storage.save_documento(doc_sem_llm)
        result = await handle_relatorio(
            ctx,
            ParsedCommand(name="relatorio", args=["diario"]),
        )
        # Total = 1, mas nenhum tier nem top-rated
        assert "1 documentos" in result.text
        assert "Top 5" not in result.text

    @pytest.mark.asyncio
    async def test_relatorio_so_docs_sem_llm_pula_top5(self) -> None:
        # Cobre branch 501->508: `rated` vazio quando todos docs têm llm=None.
        from datetime import UTC, datetime  # noqa: PLC0415

        from monitoritcd.core.models import RawItem  # noqa: PLC0415

        ctx = await _ctx()
        for hash_seed in ("e", "f"):
            raw = RawItem(
                source_id="s",
                titulo_raw=f"Sem LLM {hash_seed}",
                url=f"https://x.gov.br/{hash_seed}",
                fetched_at=datetime.now(UTC),
                content_hash=hash_seed * 64,
            )
            doc = _doc(doc_id=f"d{hash_seed}").model_copy(update={"original": raw, "llm": None})
            await ctx.storage.save_documento(doc)
        result = await handle_relatorio(
            ctx,
            ParsedCommand(name="relatorio", args=["diario"]),
        )
        assert "Top 5" not in result.text


@pytest.mark.integration
class TestBuscarRichSyntax:
    """Cobre os filtros novos do /buscar (uf, ano, tipo, severidade, limite)."""

    @pytest.mark.asyncio
    async def test_filtro_uf_filtra_por_uf(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(doc_id="d1", titulo="ITCMD doação", uf="PR"))
        await ctx.storage.save_documento(
            _doc(doc_id="d2", titulo="ITCMD doação", uf="SP").model_copy(
                update={"original": _doc(doc_id="d2").original.model_copy(
                    update={"content_hash": "b" * 64}
                )}
            )
        )
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["doação", "uf=PR"])
        )
        assert "uf\\=PR" in result.text
        assert result.pre_escaped is True

    @pytest.mark.asyncio
    async def test_filtro_uf_invalida(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["x", "uf=ZZ"])
        )
        assert result.is_error
        assert "UF inválida" in result.text

    @pytest.mark.asyncio
    async def test_filtro_ano_invalido(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["x", "ano=1900"])
        )
        assert result.is_error
        assert "intervalo" in result.text

    @pytest.mark.asyncio
    async def test_filtro_tipo_invalido(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["x", "tipo=foo"])
        )
        assert result.is_error
        assert "Tipo inválido" in result.text

    @pytest.mark.asyncio
    async def test_filtro_severidade_invalida(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["x", "severidade=foo"])
        )
        assert result.is_error
        assert "Severidade inválida" in result.text

    @pytest.mark.asyncio
    async def test_filtro_limite_fora_do_intervalo(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["x", "limite=999"])
        )
        assert result.is_error
        assert "limite" in result.text.lower()

    @pytest.mark.asyncio
    async def test_filtro_desconhecido(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["x", "desconhecido=1"])
        )
        assert result.is_error
        assert "desconhecido" in result.text.lower()

    @pytest.mark.asyncio
    async def test_card_renderiza_link_clicavel(self) -> None:
        # safe_link gera `[titulo](url)` em MarkdownV2 → Telegram renderiza clicável.
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="PL 1234/2026 ITCMD"))
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["1234"])
        )
        assert "[" in result.text and "](" in result.text  # link MarkdownV2
        assert "https://x.gov.br/" in result.text
        assert result.pre_escaped is True

    @pytest.mark.asyncio
    async def test_truncamento_indica_mais_resultados(self) -> None:
        ctx = await _ctx()
        # Insere 3 docs com hash distinto e limite=2
        for i in range(3):
            doc = _doc(doc_id=f"d{i}", titulo=f"ITCMD {i}").model_copy(
                update={
                    "original": _doc(doc_id=f"d{i}", titulo=f"ITCMD {i}").original.model_copy(
                        update={"content_hash": str(i) * 64}
                    )
                }
            )
            await ctx.storage.save_documento(doc)
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["ITCMD", "limite=2"])
        )
        assert "2\\+" in result.text  # marca de truncamento
        assert "Mostrando os primeiros 2" in result.text


@pytest.mark.integration
class TestBuscarTopicHeader:
    """Cobre branches de header e topics no resultado de /buscar."""

    @pytest.mark.asyncio
    async def test_busca_com_topic_filter_inclui_topico_no_header(self) -> None:
        # Header novo MarkdownV2: filtros aparecem como `topico\=itcd`.
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="ITCMD herança"))
        result = await handle_buscar(
            ctx,
            ParsedCommand(name="buscar", args=["ITCMD", "topico=itcd"]),
        )
        # `=` é escapado em MarkdownV2 ⇒ `\=`
        assert "topico\\=itcd" in result.text
        assert result.pre_escaped is True

    @pytest.mark.asyncio
    async def test_busca_doc_sem_llm_renderiza_titulo(self) -> None:
        # Doc sem llm: card mostra título via safe_link (clicável) + UF.
        ctx = await _ctx()
        doc_sem_llm = _doc(titulo="ITCMD direto").model_copy(update={"llm": None})
        await ctx.storage.save_documento(doc_sem_llm)
        result = await handle_buscar(
            ctx,
            ParsedCommand(name="buscar", args=["ITCMD"]),
        )
        assert "ITCMD direto" in result.text
        assert "SP" in result.text  # uf no meta
        assert result.pre_escaped is True


@pytest.mark.integration
class TestWatchAdicionarDirect:
    """Tests do `_watch_adicionar` chamado direto (não via handle_observar)."""

    @pytest.mark.asyncio
    async def test_args_insuficientes_retorna_uso(self) -> None:
        # Cobre linha 308: handle_observar prepende "adicionar", mas _watch_adicionar
        # chamado direto com args=["adicionar"] (sem termo) ainda dá Uso.
        from monitoritcd.bot.handlers import _watch_adicionar  # noqa: PLC0415

        ctx = await _ctx()
        result = await _watch_adicionar(
            ctx,
            ParsedCommand(name="observar", args=["adicionar"]),
        )
        assert result.is_error
        assert "Uso:" in result.text


class _FailingSaveStorage:
    """Storage que delega tudo para InMemoryStorage exceto save_watch (raise)."""

    def __init__(self, owner: str) -> None:
        self._inner = InMemoryStorage(owner)

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    async def save_watch(self, _watch: object) -> None:
        msg = "simulated firestore quota error"
        raise RuntimeError(msg)


class _FailingTagStorage:
    """Storage que falha em add_user_tag."""

    def __init__(self, owner: str) -> None:
        self._inner = InMemoryStorage(owner)

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    async def add_user_tag(self, _doc_id: str, _tag: str) -> None:
        msg = "simulated firestore unavailable"
        raise RuntimeError(msg)


@pytest.mark.integration
class TestObservarSaveFalha:
    @pytest.mark.asyncio
    async def test_save_watch_falha_loga_audit_failure(self) -> None:
        # Cobre 332-340: save_watch raises -> log_bot_action(result="failure")
        # + retorna erro pro user.
        ctx = BotContext(
            settings=_settings(),
            storage=_FailingSaveStorage(OWNER),  # type: ignore[arg-type]
            confirmation=TwoStepConfirmation(),
        )
        from monitoritcd.bot.handlers import _watch_adicionar  # noqa: PLC0415

        result = await _watch_adicionar(
            ctx,
            ParsedCommand(name="observar", args=["adicionar", "termo", "valido"]),
        )
        assert result.is_error
        assert "Erro:" in result.text


@pytest.mark.integration
class TestMarcarFalhas:
    @pytest.mark.asyncio
    async def test_tag_excede_max_length(self) -> None:
        # Cobre linha 416: tag > MAX_TAG_LENGTH (50 chars) é rejeitada.
        from monitoritcd.core import limits  # noqa: PLC0415

        ctx = await _ctx()
        doc = _doc()
        await ctx.storage.save_documento(doc)
        long_tag = "x" * (limits.MAX_TAG_LENGTH + 1)
        result = await handle_marcar(
            ctx,
            ParsedCommand(name="marcar", args=[doc.doc_id[:6], long_tag]),
        )
        assert result.is_error
        assert "muito longa" in result.text

    @pytest.mark.asyncio
    async def test_add_user_tag_falha_loga_audit_failure(self) -> None:
        # Cobre 437-445: add_user_tag raises -> failure path.
        failing_storage = _FailingTagStorage(OWNER)
        # Seedaa doc no inner storage para passar pela busca de prefixo.
        doc = _doc()
        await failing_storage._inner.save_documento(doc)
        ctx = BotContext(
            settings=_settings(),
            storage=failing_storage,  # type: ignore[arg-type]
            confirmation=TwoStepConfirmation(),
        )
        result = await handle_marcar(
            ctx,
            ParsedCommand(name="marcar", args=[doc.doc_id[:6], "tag"]),
        )
        assert result.is_error
        assert "Erro ao marcar" in result.text


@pytest.mark.integration
class TestConfirmarConsumeFalha:
    @pytest.mark.asyncio
    async def test_consume_lanca_token_invalido_apos_find(self) -> None:
        # Cobre 279-280: find_action retorna ação, mas consume falha
        # (race entre find e consume — token expirou no meio).
        from monitoritcd.bot.auth import (  # noqa: PLC0415
            InvalidConfirmationTokenError,
        )

        ctx = await _ctx()

        class _RacyConfirmation:
            def find_action(self, _token: str) -> str:
                return "estados.desativar:SP"

            def consume(self, _token: str, _action: str) -> None:
                msg = "token expired"
                raise InvalidConfirmationTokenError(msg)

        ctx.confirmation = _RacyConfirmation()  # type: ignore[assignment]
        result = await handle_confirmar(
            ctx,
            ParsedCommand(name="confirmar", args=["any-token"]),
        )
        assert result.is_error
        assert "inválido" in result.text.lower()
