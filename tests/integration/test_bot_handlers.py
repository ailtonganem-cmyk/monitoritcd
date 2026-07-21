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
    handle_temas,
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
        RESEND_API_KEY=SecretStr("p"),
        RESEND_FROM_EMAIL="b@example.com",
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


def _doc(
    *,
    doc_id: str = "d1",
    titulo: str = "PL ITCMD SP",
    uf: str = "SP",
    status: StatusDocumento = StatusDocumento.CLASSIFIED,
    content_hash: str = "a" * 64,
) -> Documento:
    raw = RawItem(
        source_id="s",
        titulo_raw=titulo,
        url="https://x.gov.br/",
        fetched_at=NOW,
        content_hash=content_hash,
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
        status=status,
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

    @pytest.mark.asyncio
    async def test_busca_nao_exibe_arquivado(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(
            _doc(doc_id="ativo", titulo="PL ITCMD ativo", content_hash="1" * 64)
        )
        await ctx.storage.save_documento(
            _doc(
                doc_id="arquivado",
                titulo="PL ITCMD arquivado",
                status=StatusDocumento.ARCHIVED,
                content_hash="2" * 64,
            )
        )

        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["ITCMD"]))

        assert "ativo" in result.text
        assert "arquivado" not in result.text


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
    async def test_argumento_extra_rejeitado(self) -> None:
        ctx = await _ctx()
        result = await handle_relatorio(
            ctx,
            ParsedCommand(name="relatorio", args=["diario", "lixo"]),
        )
        assert result.is_error
        assert "Uso" in result.text

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
        assert result.pre_escaped is True
        assert "Relatório Diário" in result.text
        assert "PL recente" in result.text
        assert "Resumo" in result.text

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
        assert result.pre_escaped is True
        assert "Relatório Semanal" in result.text

    @pytest.mark.asyncio
    async def test_relatorio_doc_sem_llm_aparece_como_pendente(self) -> None:
        # Doc sem LLM é contabilizado, mas fica fora do detalhamento.
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
        assert "todos pendentes" in result.text

    @pytest.mark.asyncio
    async def test_relatorio_so_docs_sem_llm_nao_renderiza_digest(self) -> None:
        # Quando todos docs têm llm=None, não há digest detalhado para renderizar.
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
        assert result.pre_escaped is False
        assert "todos pendentes" in result.text


@pytest.mark.integration
class TestTopicos:
    """Cobre /topicos — gerenciamento de topics dinâmicos (PR B)."""

    @pytest.mark.asyncio
    async def test_listar_sem_args_mostra_defaults(self) -> None:
        ctx = await _ctx()
        result = await handle_topicos(ctx, ParsedCommand(name="topicos", args=[]))
        assert "itcd" in result.text
        assert "sucessoes" in result.text
        assert "regime_bens" in result.text
        assert "nenhum" in result.text.lower()

    @pytest.mark.asyncio
    async def test_listar_explicito(self) -> None:
        ctx = await _ctx()
        result = await handle_topicos(ctx, ParsedCommand(name="topicos", args=["listar"]))
        assert "Defaults" in result.text or "defaults" in result.text.lower()

    @pytest.mark.asyncio
    async def test_subcomando_desconhecido(self) -> None:
        ctx = await _ctx()
        result = await handle_topicos(ctx, ParsedCommand(name="topicos", args=["xyz"]))
        assert result.is_error

    @pytest.mark.asyncio
    async def test_adicionar_args_insuficientes(self) -> None:
        ctx = await _ctx()
        r = await handle_topicos(ctx, ParsedCommand(name="topicos", args=["adicionar"]))
        assert r.is_error
        assert "Uso" in r.text

    @pytest.mark.asyncio
    async def test_adicionar_id_invalido(self) -> None:
        ctx = await _ctx()
        result = await handle_topicos(
            ctx,
            ParsedCommand(
                name="topicos", args=["adicionar", "1bad", "descrição válida com contexto"]
            ),
        )
        assert result.is_error
        assert "id inválido" in result.text.lower()

    @pytest.mark.asyncio
    async def test_adicionar_id_default_bloqueado(self) -> None:
        ctx = await _ctx()
        result = await handle_topicos(
            ctx,
            ParsedCommand(name="topicos", args=["adicionar", "itcd", "outra descrição válida"]),
        )
        assert result.is_error
        assert "padrão" in result.text.lower()

    @pytest.mark.asyncio
    async def test_adicionar_descricao_curta(self) -> None:
        ctx = await _ctx()
        result = await handle_topicos(
            ctx, ParsedCommand(name="topicos", args=["adicionar", "holding", "curta"])
        )
        assert result.is_error
        assert "descrição" in result.text.lower()

    @pytest.mark.asyncio
    async def test_adicionar_e_listar_extra(self) -> None:
        ctx = await _ctx()
        r1 = await handle_topicos(
            ctx,
            ParsedCommand(
                name="topicos",
                args=[
                    "adicionar",
                    "holding",
                    "Holding patrimonial e familiar para sucessão",
                ],
            ),
        )
        assert not r1.is_error
        assert "holding" in r1.text

        r2 = await handle_topicos(ctx, ParsedCommand(name="topicos", args=["listar"]))
        assert "holding" in r2.text
        assert "Holding patrimonial" in r2.text

    @pytest.mark.asyncio
    async def test_adicionar_duplicado_avisa(self) -> None:
        ctx = await _ctx()
        await handle_topicos(
            ctx,
            ParsedCommand(
                name="topicos", args=["adicionar", "trusts", "Trusts e estruturas offshore"]
            ),
        )
        r = await handle_topicos(
            ctx,
            ParsedCommand(
                name="topicos", args=["adicionar", "trusts", "Outra descrição válida aqui"]
            ),
        )
        assert "já existe" in r.text.lower()

    @pytest.mark.asyncio
    async def test_remover_args_insuficientes(self) -> None:
        ctx = await _ctx()
        r = await handle_topicos(ctx, ParsedCommand(name="topicos", args=["remover"]))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_remover_default_bloqueado(self) -> None:
        ctx = await _ctx()
        r = await handle_topicos(ctx, ParsedCommand(name="topicos", args=["remover", "itcd"]))
        assert r.is_error
        assert "padrão" in r.text.lower()

    @pytest.mark.asyncio
    async def test_remover_inexistente_avisa(self) -> None:
        ctx = await _ctx()
        r = await handle_topicos(ctx, ParsedCommand(name="topicos", args=["remover", "nao_existe"]))
        assert "não encontrado" in r.text.lower()

    @pytest.mark.asyncio
    async def test_remover_existente(self) -> None:
        ctx = await _ctx()
        await handle_topicos(
            ctx,
            ParsedCommand(
                name="topicos", args=["adicionar", "previdencia", "Previdência privada VGBL/PGBL"]
            ),
        )
        r = await handle_topicos(
            ctx, ParsedCommand(name="topicos", args=["remover", "previdencia"])
        )
        assert not r.is_error
        assert "removido" in r.text.lower()

    @pytest.mark.asyncio
    async def test_excede_limite(self) -> None:
        # Cobre branch `len(cfg.topics) >= MAX_EXTRA_TOPICS`.
        from monitoritcd.core import limits as _lim  # noqa: PLC0415
        from monitoritcd.core.models import ExtraTopicsConfig, TopicEntry  # noqa: PLC0415

        ctx = await _ctx()
        full = ExtraTopicsConfig(
            owner_id=OWNER,
            topics=[
                TopicEntry(
                    id=f"topico_{i:02d}",
                    descricao="Descrição genérica para preencher o limite",
                    criado_em=NOW,
                    criado_por="seed",
                )
                for i in range(_lim.MAX_EXTRA_TOPICS)
            ],
            updated_at=NOW,
            updated_by="seed",
        )
        await ctx.storage.save_extra_topics(full)
        r = await handle_topicos(
            ctx,
            ParsedCommand(
                name="topicos",
                args=["adicionar", "extra_excede", "Descrição válida que excede o limite"],
            ),
        )
        assert r.is_error
        assert "limite" in r.text.lower()


@pytest.mark.integration
class TestTemas:
    """Cobre /temas — gerenciamento de keywords extras dinâmicas."""

    @pytest.mark.asyncio
    async def test_uso_sem_subcomando(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=[]))
        assert result.is_error
        assert "Uso" in result.text

    @pytest.mark.asyncio
    async def test_subcomando_desconhecido(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["xyz"]))
        assert result.is_error
        assert "desconhecido" in result.text.lower()

    @pytest.mark.asyncio
    async def test_listar_vazio(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["listar"]))
        assert "nenhuma" in result.text.lower()
        assert result.pre_escaped is True

    @pytest.mark.asyncio
    async def test_adicionar_e_listar(self) -> None:
        ctx = await _ctx()
        r1 = await handle_temas(
            ctx,
            ParsedCommand(name="temas", args=["adicionar", "trust internacional"]),
        )
        assert not r1.is_error
        assert "adicionada" in r1.text.lower()

        r2 = await handle_temas(ctx, ParsedCommand(name="temas", args=["listar"]))
        assert "trust internacional" in r2.text

    @pytest.mark.asyncio
    async def test_adicionar_com_topico(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(
            ctx,
            ParsedCommand(
                name="temas", args=["adicionar", "holding", "patrimonial", "topico=itcd"]
            ),
        )
        assert not result.is_error
        assert "itcd" in result.text

        cfg = await ctx.storage.get_extra_keywords()
        assert cfg is not None
        assert "holding patrimonial" in cfg.keywords_by_topic["itcd"]

    @pytest.mark.asyncio
    async def test_adicionar_termo_curto_falha(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "ab"]))
        assert result.is_error
        assert "chars" in result.text.lower()

    @pytest.mark.asyncio
    async def test_adicionar_topic_invalido(self) -> None:
        # Topic precisa começar com letra minúscula. "1abc" começa com dígito.
        ctx = await _ctx()
        result = await handle_temas(
            ctx, ParsedCommand(name="temas", args=["adicionar", "termo válido", "topico=1abc"])
        )
        assert result.is_error
        assert "tópico inválido" in result.text.lower() or "topico inválido" in result.text.lower()

    @pytest.mark.asyncio
    async def test_adicionar_termo_em_default_avisa(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "ITCMD"]))
        # ITCMD já está nos defaults.
        assert "defaults" in result.text.lower()

    @pytest.mark.asyncio
    async def test_adicionar_duplicado_extras_avisa(self) -> None:
        ctx = await _ctx()
        await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo único"]))
        r2 = await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo único"]))
        assert "extras" in r2.text.lower()

    @pytest.mark.asyncio
    async def test_remover_termo_existente(self) -> None:
        ctx = await _ctx()
        await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo a remover"]))
        result = await handle_temas(
            ctx, ParsedCommand(name="temas", args=["remover", "termo a remover"])
        )
        assert not result.is_error
        assert "removido" in result.text.lower()

        cfg = await ctx.storage.get_extra_keywords()
        assert cfg is not None
        assert cfg.total_count() == 0

    @pytest.mark.asyncio
    async def test_remover_inexistente_avisa(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(
            ctx, ParsedCommand(name="temas", args=["remover", "inexistente"])
        )
        assert "nenhuma" in result.text.lower()

    @pytest.mark.asyncio
    async def test_reset_global(self) -> None:
        ctx = await _ctx()
        await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo um"]))
        await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo dois"]))
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["reset"]))
        assert "removidas" in result.text.lower()

        cfg = await ctx.storage.get_extra_keywords()
        assert cfg is not None
        assert cfg.total_count() == 0

    @pytest.mark.asyncio
    async def test_adicionar_args_insuficientes(self) -> None:
        # Cobre `len(cmd.args) < MIN_ARGS_WITH_UF` em _temas_adicionar.
        ctx = await _ctx()
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar"]))
        assert result.is_error
        assert "Uso" in result.text

    @pytest.mark.asyncio
    async def test_adicionar_so_topico_sem_termo(self) -> None:
        # Cobre `if not termo` após _parse_temas_args.
        ctx = await _ctx()
        result = await handle_temas(
            ctx, ParsedCommand(name="temas", args=["adicionar", "topico=itcd"])
        )
        assert result.is_error
        assert "termo" in result.text.lower()

    @pytest.mark.asyncio
    async def test_remover_args_insuficientes(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["remover"]))
        assert result.is_error
        assert "Uso" in result.text

    @pytest.mark.asyncio
    async def test_remover_sem_termo_apos_topico(self) -> None:
        ctx = await _ctx()
        await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo extra"]))
        result = await handle_temas(
            ctx, ParsedCommand(name="temas", args=["remover", "topico=geral"])
        )
        assert result.is_error
        assert "termo" in result.text.lower()

    @pytest.mark.asyncio
    async def test_remover_global_termo_em_apenas_um_topico(self) -> None:
        # Cobre branch onde NÃO há filtro de topic e o termo está só em UM topic
        # mas existem outros topics intactos (linha 865: new_by_topic[t] = list(kws)).
        from monitoritcd.core.models import ExtraKeywordsConfig  # noqa: PLC0415

        ctx = await _ctx()
        cfg = ExtraKeywordsConfig(
            owner_id=OWNER,
            keywords_by_topic={"itcd": ["alvo remover"], "geral": ["preservado"]},
            updated_at=NOW,
            updated_by="seed",
        )
        await ctx.storage.save_extra_keywords(cfg)
        result = await handle_temas(
            ctx, ParsedCommand(name="temas", args=["remover", "alvo remover"])
        )
        assert not result.is_error
        new_cfg = await ctx.storage.get_extra_keywords()
        assert new_cfg is not None
        assert "preservado" in new_cfg.keywords_by_topic["geral"]
        assert "alvo remover" not in new_cfg.keywords_by_topic.get("itcd", [])

    @pytest.mark.asyncio
    async def test_remover_em_topico_especifico_sem_match(self) -> None:
        # Cobre branch onde topic é fornecido mas o termo não está nele.
        ctx = await _ctx()
        await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo geral"]))
        result = await handle_temas(
            ctx,
            ParsedCommand(name="temas", args=["remover", "termo geral", "topico=itcd"]),
        )
        # Não está no topic itcd → mensagem "não encontrado".
        assert "não encontrado" in result.text.lower()

    @pytest.mark.asyncio
    async def test_reset_sem_extras(self) -> None:
        ctx = await _ctx()
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["reset"]))
        assert "nenhuma" in result.text.lower()

    @pytest.mark.asyncio
    async def test_reset_topico_inexistente(self) -> None:
        ctx = await _ctx()
        await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo geral"]))
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["reset", "topico=itcd"]))
        assert "não tem" in result.text.lower() or "nao tem" in result.text.lower()

    @pytest.mark.asyncio
    async def test_adicionar_excede_limite_total(self) -> None:
        # Cobre branch `cfg.total_count() >= MAX_EXTRA_KEYWORDS_TOTAL`.
        from monitoritcd.core import limits as _lim  # noqa: PLC0415
        from monitoritcd.core.models import ExtraKeywordsConfig  # noqa: PLC0415

        ctx = await _ctx()
        full = ExtraKeywordsConfig(
            owner_id=OWNER,
            keywords_by_topic={
                "geral": [f"termo_{i:03d}" for i in range(_lim.MAX_EXTRA_KEYWORDS_TOTAL)]
            },
            updated_at=NOW,
            updated_by="seed",
        )
        await ctx.storage.save_extra_keywords(full)
        result = await handle_temas(
            ctx, ParsedCommand(name="temas", args=["adicionar", "novo termo extra"])
        )
        assert result.is_error
        assert "limite" in result.text.lower()

    @pytest.mark.asyncio
    async def test_listar_com_topic_vazio_skip(self) -> None:
        # Cobre `if not kws: continue` no _temas_listar.
        from monitoritcd.core.models import ExtraKeywordsConfig  # noqa: PLC0415

        ctx = await _ctx()
        cfg = ExtraKeywordsConfig(
            owner_id=OWNER,
            keywords_by_topic={"itcd": ["termo válido"], "vazio": []},
            updated_at=NOW,
            updated_by="seed",
        )
        await ctx.storage.save_extra_keywords(cfg)
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["listar"]))
        assert "termo válido" in result.text
        # Topic "vazio" não aparece no header (sem keywords).
        assert "vazio" not in result.text

    @pytest.mark.asyncio
    async def test_reset_topico_especifico(self) -> None:
        ctx = await _ctx()
        await handle_temas(
            ctx, ParsedCommand(name="temas", args=["adicionar", "termo itcd", "topico=itcd"])
        )
        await handle_temas(ctx, ParsedCommand(name="temas", args=["adicionar", "termo geral"]))
        result = await handle_temas(ctx, ParsedCommand(name="temas", args=["reset", "topico=itcd"]))
        assert "itcd" in result.text.lower()
        cfg = await ctx.storage.get_extra_keywords()
        assert cfg is not None
        assert "termo geral" in cfg.keywords_by_topic["geral"]
        assert "itcd" not in cfg.keywords_by_topic


@pytest.mark.integration
class TestBuscarRichSyntax:
    """Cobre os filtros novos do /buscar (uf, ano, tipo, severidade, limite)."""

    @pytest.mark.asyncio
    async def test_filtro_uf_filtra_por_uf(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(doc_id="d1", titulo="ITCMD doação", uf="PR"))
        await ctx.storage.save_documento(
            _doc(doc_id="d2", titulo="ITCMD doação", uf="SP").model_copy(
                update={
                    "original": _doc(doc_id="d2").original.model_copy(
                        update={"content_hash": "b" * 64}
                    )
                }
            )
        )
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["doação", "uf=PR"]))
        assert "uf\\=PR" in result.text
        assert result.pre_escaped is True

    @pytest.mark.asyncio
    async def test_filtro_uf_invalida(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["x", "uf=ZZ"]))
        assert result.is_error
        assert "UF inválida" in result.text

    @pytest.mark.asyncio
    async def test_filtro_ano_invalido(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["x", "ano=1900"]))
        assert result.is_error
        assert "intervalo" in result.text

    @pytest.mark.asyncio
    async def test_filtro_tipo_invalido(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["x", "tipo=foo"]))
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
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["x", "limite=999"]))
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
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["1234"]))
        assert "](" in result.text  # link MarkdownV2: [titulo](url)
        # Extrai URL do link e valida via parse, evitando substring-only check
        # (que CodeQL flagueia como py/incomplete-url-substring-sanitization).
        import re  # noqa: PLC0415
        from urllib.parse import urlparse  # noqa: PLC0415

        m = re.search(r"\]\((https?://[^)]+)\)", result.text)
        assert m is not None
        parsed_url = urlparse(m.group(1))
        assert parsed_url.scheme == "https"
        assert parsed_url.netloc == "x.gov.br"
        assert result.pre_escaped is True

    @pytest.mark.asyncio
    async def test_filtro_valor_vazio(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["x", "uf="]))
        assert result.is_error
        assert "vazio" in result.text

    @pytest.mark.asyncio
    async def test_filtro_uf_federal(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["x", "uf=_federal"]))
        # Sem docs → "Nenhum resultado", mas não é erro
        assert not result.is_error
        # `_` escapado em MarkdownV2 ⇒ `\_federal`
        assert "uf\\=\\_federal" in result.text

    @pytest.mark.asyncio
    async def test_filtro_ano_valido_com_match(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="ITCMD 2026"))
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["ITCMD", "ano=2026"]))
        assert "ano\\=2026" in result.text
        assert "ITCMD 2026" in result.text

    @pytest.mark.asyncio
    async def test_filtro_ano_corta_doc_fora_da_janela(self) -> None:
        # Doc de 2026-04-24 não casa com ano=2025 (until cutoff).
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="ITCMD doc"))
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["ITCMD", "ano=2025"]))
        assert "Nenhum resultado" in result.text

    @pytest.mark.asyncio
    async def test_filtro_tipo_valido(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="ITCMD PL"))
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["ITCMD", "tipo=projeto_lei"])
        )
        # `_` é escapado em MarkdownV2 ⇒ `projeto\_lei`
        assert "tipo\\=projeto\\_lei" in result.text
        assert "ITCMD PL" in result.text

    @pytest.mark.asyncio
    async def test_filtro_severidade_valida(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="ITCMD alta"))
        result = await handle_buscar(
            ctx, ParsedCommand(name="buscar", args=["ITCMD", "severidade=alta"])
        )
        assert "severidade\\=alta" in result.text
        assert "ITCMD alta" in result.text

    @pytest.mark.asyncio
    async def test_filtro_limite_valido(self) -> None:
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="ITCMD lim"))
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["ITCMD", "limite=5"]))
        assert not result.is_error
        assert "ITCMD lim" in result.text

    @pytest.mark.asyncio
    async def test_combinacao_de_filtros(self) -> None:
        # Cobre o branch onde todos os filtros são montados no header.
        ctx = await _ctx()
        await ctx.storage.save_documento(_doc(titulo="ITCMD combo"))
        result = await handle_buscar(
            ctx,
            ParsedCommand(
                name="buscar",
                args=[
                    "ITCMD",
                    "uf=SP",
                    "ano=2026",
                    "topico=itcd",
                    "tipo=projeto_lei",
                    "severidade=alta",
                ],
            ),
        )
        for marker in [
            "uf\\=SP",
            "ano\\=2026",
            "topico\\=itcd",
            "tipo\\=projeto\\_lei",  # underscore escapado
            "severidade\\=alta",
        ]:
            assert marker in result.text

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
        result = await handle_buscar(ctx, ParsedCommand(name="buscar", args=["ITCMD", "limite=2"]))
        assert "2\\+" in result.text  # marca de truncamento
        assert "Mostrando os primeiros 2" in result.text

    @pytest.mark.asyncio
    async def test_busca_encontra_match_apos_mil_documentos(self) -> None:
        from datetime import timedelta  # noqa: PLC0415

        ctx = await _ctx()
        for i in range(1005):
            raw = RawItem(
                source_id="s",
                titulo_raw=f"Documento ordinário {i}",
                url=f"https://x.gov.br/{i}",
                fetched_at=NOW + timedelta(minutes=i),
                content_hash=f"{i:064x}"[-64:],
            )
            await ctx.storage.save_documento(
                _doc(doc_id=f"n{i}").model_copy(update={"original": raw})
            )

        target_raw = RawItem(
            source_id="s",
            titulo_raw="Parecer raro sobre herança digital",
            url="https://x.gov.br/target",
            fetched_at=NOW - timedelta(days=30),
            content_hash="f" * 64,
        )
        target = _doc(doc_id="target").model_copy(update={"original": target_raw})
        assert target.llm is not None
        target.llm.resumo_completo = "Discussão de herança digital e ITCMD."
        await ctx.storage.save_documento(target)

        result = await handle_buscar(
            ctx,
            ParsedCommand(name="buscar", args=["heranca", "digital"]),
        )

        assert "Parecer raro" in result.text


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
