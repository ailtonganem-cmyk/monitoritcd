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
    handle_observar,
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
    async def test_busca_so_com_filtro_topico_falha(self) -> None:
        ctx = await _ctx()
        result = await handle_buscar(
            ctx,
            ParsedCommand(name="buscar", args=["topico=itcd"]),
        )
        assert result.is_error
        assert "termo" in result.text.lower()


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
