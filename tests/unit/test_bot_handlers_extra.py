"""Testes dos handlers extra do bot (Categoria 6 IDEAS.md)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from monitoritcd.bot.auth import TwoStepConfirmation
from monitoritcd.bot.handlers import BotContext, ParsedCommand
from monitoritcd.bot.handlers_extra import (
    handle_arquivo,
    handle_backup,
    handle_cancelar,
    handle_coleta,
    handle_comentar,
    handle_desmarcar,
    handle_diff,
    handle_export,
    handle_favoritar,
    handle_favoritos,
    handle_fontes,
    handle_historico,
    handle_lembrar,
    handle_quota,
    handle_reprocessar,
    handle_silenciar,
    handle_tags,
)
from monitoritcd.core.config import Settings
from monitoritcd.core.models import (
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
from monitoritcd.storage.in_memory import InMemoryStorage

NOW = datetime(2026, 4, 24, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(
        OWNER_ID="o",
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


async def _ctx_with_doc(doc_id: str = "test-doc", *, with_llm: bool = True) -> BotContext:
    storage = InMemoryStorage(owner_id="o")
    raw = RawItem(
        source_id="src",
        titulo_raw="Teste",
        url="https://x.gov.br/",
        fetched_at=NOW,
        data_publicacao=NOW,
        content_hash="a" * 64,
    )
    src = Source(
        id="src",
        uf="SP",
        nome="x",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
    )
    llm = (
        LLMResult(
            classified_at=NOW,
            llm_model="x",
            llm_prompt_version="v1",
            tipo=TipoAto.PROJETO_LEI,
            relevancia=8,
            severity_tier=SeverityTier.ALTA,
            resumo="r",
        )
        if with_llm
        else None
    )
    doc = Documento(
        owner_id="o",
        doc_id=doc_id,
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )
    await storage.save_documento(doc)
    return BotContext(settings=_settings(), storage=storage, confirmation=TwoStepConfirmation())


def _cmd(name: str, *args: str) -> ParsedCommand:
    return ParsedCommand(name=name, args=list(args))


@pytest.mark.unit
class TestSilenciar:
    @pytest.mark.asyncio
    async def test_listar_vazio(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "listar"))
        assert "Nenhum" in r.text

    @pytest.mark.asyncio
    async def test_uf_format(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "UF=SP", "7d"))
        assert "Silenciamento" in r.text

    @pytest.mark.asyncio
    async def test_uf_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "UF=XX", "7d"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_duracao_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "UF=SP", "abc"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_sem_args(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar"))
        assert r.is_error


@pytest.mark.unit
class TestDesmarcar:
    @pytest.mark.asyncio
    async def test_doc_inexistente(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_desmarcar(ctx, _cmd("desmarcar", "nonexistent", "tag1"))
        assert r.is_error


@pytest.mark.unit
class TestTags:
    @pytest.mark.asyncio
    async def test_listar_vazio(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_tags(ctx, _cmd("tags", "listar"))
        assert "Nenhuma" in r.text

    @pytest.mark.asyncio
    async def test_renomear_requer_confirmacao(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_tags(ctx, _cmd("tags", "renomear", "old", "new"))
        assert "Confirma" in r.text


@pytest.mark.unit
class TestFavoritos:
    @pytest.mark.asyncio
    async def test_favoritar_doc_valido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_favoritar(ctx, _cmd("favoritar", "test-doc"))
        assert "favoritado" in r.text.lower()

    @pytest.mark.asyncio
    async def test_listar_favoritos(self) -> None:
        ctx = await _ctx_with_doc()
        await handle_favoritar(ctx, _cmd("favoritar", "test-doc"))
        r = await handle_favoritos(ctx, _cmd("favoritos"))
        assert "test-doc" in r.text


@pytest.mark.unit
class TestArquivo:
    @pytest.mark.asyncio
    async def test_por_uf(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo", "UF=SP"))
        assert "1 docs" in r.text or "Teste" in r.text


@pytest.mark.unit
class TestFontes:
    @pytest.mark.asyncio
    async def test_listar(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "listar"))
        assert "src" in r.text or "Fontes" in r.text

    @pytest.mark.asyncio
    async def test_status(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "status"))
        assert "Status" in r.text


@pytest.mark.unit
class TestReprocessar:
    @pytest.mark.asyncio
    async def test_data_valida_emite_token(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_reprocessar(ctx, _cmd("reprocessar", "2026-04-01"))
        assert "confirmar" in r.text.lower()

    @pytest.mark.asyncio
    async def test_data_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_reprocessar(ctx, _cmd("reprocessar", "abc"))
        assert r.is_error


@pytest.mark.unit
class TestBackupColetaQuota:
    @pytest.mark.asyncio
    async def test_backup_emite_token(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_backup(ctx, _cmd("backup"))
        assert "confirmar" in r.text.lower()

    @pytest.mark.asyncio
    async def test_coleta(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_coleta(ctx, _cmd("coleta"))
        assert "actions" in r.text.lower() or "GitHub" in r.text

    @pytest.mark.asyncio
    async def test_quota(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_quota(ctx, _cmd("quota"))
        assert "Cotas" in r.text


@pytest.mark.unit
class TestExport:
    @pytest.mark.asyncio
    async def test_csv_data_valida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_export(ctx, _cmd("export", "csv", "2026-01-01"))
        assert "csv" in r.text.lower()

    @pytest.mark.asyncio
    async def test_formato_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_export(ctx, _cmd("export", "xml", "2026-01-01"))
        assert r.is_error


@pytest.mark.unit
class TestDiffHistorico:
    @pytest.mark.asyncio
    async def test_diff_doc_inexistente(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_diff(ctx, _cmd("diff", "test-doc", "outro"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_historico_doc_valido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_historico(ctx, _cmd("historico", "test-doc"))
        assert "Coletado" in r.text


@pytest.mark.unit
class TestComentarLembrarCancelar:
    @pytest.mark.asyncio
    async def test_comentar(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_comentar(ctx, _cmd("comentar", "test-doc", "isso é um teste"))
        assert "Comentário salvo" in r.text

    @pytest.mark.asyncio
    async def test_lembrar_data_valida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_lembrar(ctx, _cmd("lembrar", "revisar", "2026-12-31"))
        assert "Lembrete" in r.text

    @pytest.mark.asyncio
    async def test_cancelar(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_cancelar(ctx, _cmd("cancelar"))
        assert "expira" in r.text.lower() or "cancel" in r.text.lower()


@pytest.mark.unit
class TestExtraRegistration:
    def test_dispatch_includes_new_commands(self) -> None:
        """Verifica que HANDLERS incorpora os novos handlers."""
        from monitoritcd.bot.handlers import HANDLERS  # noqa: PLC0415

        for cmd_name in (
            "silenciar",
            "desmarcar",
            "tags",
            "favoritar",
            "favoritos",
            "arquivo",
            "fontes",
            "reprocessar",
            "backup",
            "coleta",
            "export",
            "quota",
            "diff",
            "historico",
            "comentar",
            "lembrar",
            "cancelar",
        ):
            assert cmd_name in HANDLERS, f"comando {cmd_name} não registrado"
