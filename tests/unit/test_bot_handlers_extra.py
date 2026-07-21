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
    handle_sefazmg,
    handle_silenciar,
    handle_tags,
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
    async def test_listar_com_silenciamentos(self) -> None:
        """Cobre o ramo de listagem com itens presentes em silenced_until."""
        ctx = await _ctx_with_doc()
        await ctx.storage.save_active_states(
            ActiveStatesConfig(
                owner_id="o",
                active_uf=["SP"],
                silenced_until={"SP": NOW},
                updated_at=NOW,
                updated_by="test",
            )
        )
        r = await handle_silenciar(ctx, _cmd("silenciar", "listar"))
        assert "SP" in r.text

    @pytest.mark.asyncio
    async def test_uf_format(self) -> None:
        # V5 (Pentest): persistência requer ActiveStatesConfig pré-existente
        from datetime import UTC, datetime  # noqa: PLC0415

        from monitoritcd.core.models import ActiveStatesConfig  # noqa: PLC0415

        ctx = await _ctx_with_doc()
        await ctx.storage.save_active_states(
            ActiveStatesConfig(
                owner_id="o",
                active_uf=["SP"],
                updated_at=datetime.now(UTC),
                updated_by="test",
            )
        )
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

    @pytest.mark.asyncio
    async def test_chave_invalida(self) -> None:
        """chave=valor com chave fora de {UF, tipo, tag}."""
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "outra=x", "7d"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_config_inicial_nao_criada(self) -> None:
        """chave=valor válido mas sem ActiveStatesConfig ainda persistida."""
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "tipo=noticia", "1d"))
        assert r.is_error
        assert "inicial" in r.text.lower()

    @pytest.mark.asyncio
    async def test_argumentos_invalidos_fallback(self) -> None:
        """Sub sem '=' e diferente de listar/remover cai no fallback genérico."""
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "qualquercoisa"))
        assert r.is_error
        assert "inválidos" in r.text.lower()

    @pytest.mark.asyncio
    async def test_remover_sem_args_suficientes(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "remover"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_remover_chave_nao_ativa(self) -> None:
        """active existe mas chave não está em silenced_until."""
        ctx = await _ctx_with_doc()
        await ctx.storage.save_active_states(
            ActiveStatesConfig(
                owner_id="o",
                active_uf=["SP"],
                updated_at=NOW,
                updated_by="test",
            )
        )
        r = await handle_silenciar(ctx, _cmd("silenciar", "remover", "SP"))
        assert "não estava ativo" in r.text

    @pytest.mark.asyncio
    async def test_remover_sem_config(self) -> None:
        """active is None -> mesma mensagem de 'não estava ativo'."""
        ctx = await _ctx_with_doc()
        r = await handle_silenciar(ctx, _cmd("silenciar", "remover", "SP"))
        assert "não estava ativo" in r.text

    @pytest.mark.asyncio
    async def test_remover_com_sucesso(self) -> None:
        ctx = await _ctx_with_doc()
        await ctx.storage.save_active_states(
            ActiveStatesConfig(
                owner_id="o",
                active_uf=["SP"],
                silenced_until={"SP": NOW},
                updated_at=NOW,
                updated_by="test",
            )
        )
        r = await handle_silenciar(ctx, _cmd("silenciar", "remover", "SP"))
        assert "removido" in r.text
        active = await ctx.storage.get_active_states()
        assert active is not None
        assert "SP" not in active.silenced_until


@pytest.mark.unit
class TestDesmarcar:
    @pytest.mark.asyncio
    async def test_doc_inexistente(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_desmarcar(ctx, _cmd("desmarcar", "nonexistent", "tag1"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_args_insuficientes(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_desmarcar(ctx, _cmd("desmarcar", "test-doc"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_doc_id_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_desmarcar(ctx, _cmd("desmarcar", "a", "tag1"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_tag_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_desmarcar(ctx, _cmd("desmarcar", "test-doc", "tag inválida!"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_tag_nao_estava_no_doc(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_desmarcar(ctx, _cmd("desmarcar", "test-doc", "naoexiste"))
        assert "não estava" in r.text

    @pytest.mark.asyncio
    async def test_remove_tag_existente(self) -> None:
        ctx = await _ctx_with_doc()
        await ctx.storage.add_user_tag("test-doc", "minhatag")
        r = await handle_desmarcar(ctx, _cmd("desmarcar", "test-doc", "minhatag"))
        assert "removida" in r.text
        doc = await ctx.storage.get_documento("test-doc")
        assert doc is not None
        assert "minhatag" not in doc.user_tags


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

    @pytest.mark.asyncio
    async def test_listar_com_tags(self) -> None:
        ctx = await _ctx_with_doc()
        await ctx.storage.add_user_tag("test-doc", "urgente")
        r = await handle_tags(ctx, _cmd("tags", "listar"))
        assert "urgente" in r.text

    @pytest.mark.asyncio
    async def test_renomear_args_insuficientes(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_tags(ctx, _cmd("tags", "renomear", "old"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_renomear_tag_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_tags(ctx, _cmd("tags", "renomear", "old!", "new"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_subcomando_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_tags(ctx, _cmd("tags", "outro"))
        assert r.is_error


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

    @pytest.mark.asyncio
    async def test_favoritar_sem_args(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_favoritar(ctx, _cmd("favoritar"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_favoritar_doc_id_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_favoritar(ctx, _cmd("favoritar", "a"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_favoritar_doc_inexistente(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_favoritar(ctx, _cmd("favoritar", "nao-existe"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_favoritos_vazio(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_favoritos(ctx, _cmd("favoritos"))
        assert "Nenhum favorito" in r.text

    @pytest.mark.asyncio
    async def test_favoritos_mais_de_20(self) -> None:
        storage = InMemoryStorage(owner_id="o")
        ctx = BotContext(settings=_settings(), storage=storage, confirmation=TwoStepConfirmation())
        for i in range(22):
            doc_id = f"doc-{i}"
            raw = RawItem(
                source_id="src",
                titulo_raw=f"Teste {i}",
                url=f"https://x.gov.br/{i}",
                fetched_at=NOW,
                data_publicacao=NOW,
                content_hash=f"{i:064d}",
            )
            src = Source(
                id="src",
                uf="SP",
                nome="x",
                tipo=TipoFonte.ASSEMBLEIA,
                parser=Parser.GENERIC_HTML,
                url="https://x.gov.br/",
            )
            doc = Documento(
                owner_id="o",
                doc_id=doc_id,
                source=src,
                original=raw,
                llm=None,
                status=StatusDocumento.PENDING,
                user_tags=["favorito"],
            )
            await storage.save_documento(doc)
        r = await handle_favoritos(ctx, _cmd("favoritos"))
        assert "mais" in r.text


@pytest.mark.unit
class TestArquivo:
    @pytest.mark.asyncio
    async def test_por_uf(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo", "UF=SP"))
        assert "1 docs" in r.text or "Teste" in r.text

    @pytest.mark.asyncio
    async def test_sem_args(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_sem_igual(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo", "SP"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_mes_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo", "mes=abc"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_mes_valido_com_match(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo", f"mes={NOW.year:04d}-{NOW.month:02d}"))
        assert "Teste" in r.text

    @pytest.mark.asyncio
    async def test_uf_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo", "UF=XX"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_chave_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo", "ano=2026"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_sem_resultados(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_arquivo(ctx, _cmd("arquivo", "UF=RJ"))
        assert "Nenhum documento" in r.text

    @pytest.mark.asyncio
    async def test_mais_de_20_resultados(self) -> None:
        storage = InMemoryStorage(owner_id="o")
        ctx = BotContext(settings=_settings(), storage=storage, confirmation=TwoStepConfirmation())
        for i in range(22):
            raw = RawItem(
                source_id="src",
                titulo_raw=f"Teste {i}",
                url=f"https://x.gov.br/{i}",
                fetched_at=NOW,
                data_publicacao=NOW,
                content_hash=f"{i:064d}",
            )
            src = Source(
                id="src",
                uf="SP",
                nome="x",
                tipo=TipoFonte.ASSEMBLEIA,
                parser=Parser.GENERIC_HTML,
                url="https://x.gov.br/",
            )
            doc = Documento(
                owner_id="o",
                doc_id=f"doc-{i}",
                source=src,
                original=raw,
                llm=None,
                status=StatusDocumento.PENDING,
            )
            await storage.save_documento(doc)
        r = await handle_arquivo(ctx, _cmd("arquivo", "UF=SP"))
        assert "mais" in r.text


@pytest.mark.unit
class TestFontes:
    @pytest.mark.asyncio
    async def test_listar(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "listar"))
        assert "src" in r.text or "Fontes" in r.text

    @pytest.mark.asyncio
    async def test_listar_sem_docs(self) -> None:
        storage = InMemoryStorage(owner_id="o")
        ctx = BotContext(settings=_settings(), storage=storage, confirmation=TwoStepConfirmation())
        r = await handle_fontes(ctx, _cmd("fontes", "listar"))
        assert "Nenhum documento" in r.text

    @pytest.mark.asyncio
    async def test_status(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "status"))
        assert "Status" in r.text

    @pytest.mark.asyncio
    async def test_ativar_sem_source_id(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "ativar"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_ativar_source_id_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "ativar", "!!"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_ativar_com_sucesso(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "ativar", "sefaz-sp"))
        assert "sefaz-sp" in r.text

    @pytest.mark.asyncio
    async def test_desativar_com_sucesso(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "desativar", "sefaz-sp"))
        assert "sefaz-sp" in r.text

    @pytest.mark.asyncio
    async def test_subcomando_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_fontes(ctx, _cmd("fontes", "outro"))
        assert r.is_error


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

    @pytest.mark.asyncio
    async def test_sem_args(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_reprocessar(ctx, _cmd("reprocessar"))
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

    @pytest.mark.asyncio
    async def test_args_insuficientes(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_export(ctx, _cmd("export", "csv"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_data_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_export(ctx, _cmd("export", "csv", "abc"))
        assert r.is_error


@pytest.mark.unit
class TestDiffHistorico:
    @pytest.mark.asyncio
    async def test_diff_doc_inexistente(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_diff(ctx, _cmd("diff", "test-doc", "outro"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_diff_args_insuficientes(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_diff(ctx, _cmd("diff", "test-doc"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_diff_doc_id_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_diff(ctx, _cmd("diff", "a", "b"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_diff_com_sucesso_e_llm(self) -> None:
        storage = InMemoryStorage(owner_id="o")
        ctx = BotContext(settings=_settings(), storage=storage, confirmation=TwoStepConfirmation())
        src = Source(
            id="src",
            uf="SP",
            nome="x",
            tipo=TipoFonte.ASSEMBLEIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        for doc_id, hash_prefix in (("doc-a", "a"), ("doc-b", "b")):
            raw = RawItem(
                source_id="src",
                titulo_raw=f"Titulo {doc_id}",
                url="https://x.gov.br/",
                fetched_at=NOW,
                data_publicacao=NOW,
                content_hash=hash_prefix * 64,
            )
            llm = LLMResult(
                classified_at=NOW,
                llm_model="x",
                llm_prompt_version="v1",
                tipo=TipoAto.PROJETO_LEI,
                relevancia=8,
                severity_tier=SeverityTier.ALTA,
                resumo="r",
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
        r = await handle_diff(ctx, _cmd("diff", "doc-a", "doc-b"))
        assert "Relevância" in r.text
        assert "Tier" in r.text

    @pytest.mark.asyncio
    async def test_diff_um_doc_sem_llm(self) -> None:
        """Quando só um dos docs tem `llm`, a seção de relevância/tier é omitida."""
        storage = InMemoryStorage(owner_id="o")
        ctx = BotContext(settings=_settings(), storage=storage, confirmation=TwoStepConfirmation())
        src = Source(
            id="src",
            uf="SP",
            nome="x",
            tipo=TipoFonte.ASSEMBLEIA,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        raw_a = RawItem(
            source_id="src",
            titulo_raw="Titulo A",
            url="https://x.gov.br/",
            fetched_at=NOW,
            data_publicacao=NOW,
            content_hash="a" * 64,
        )
        raw_b = RawItem(
            source_id="src",
            titulo_raw="Titulo B",
            url="https://x.gov.br/",
            fetched_at=NOW,
            data_publicacao=NOW,
            content_hash="b" * 64,
        )
        llm = LLMResult(
            classified_at=NOW,
            llm_model="x",
            llm_prompt_version="v1",
            tipo=TipoAto.PROJETO_LEI,
            relevancia=8,
            severity_tier=SeverityTier.ALTA,
            resumo="r",
        )
        doc_a = Documento(
            owner_id="o",
            doc_id="doc-a",
            source=src,
            original=raw_a,
            llm=llm,
            status=StatusDocumento.CLASSIFIED,
        )
        doc_b = Documento(
            owner_id="o",
            doc_id="doc-b",
            source=src,
            original=raw_b,
            llm=None,
            status=StatusDocumento.PENDING,
        )
        await storage.save_documento(doc_a)
        await storage.save_documento(doc_b)
        r = await handle_diff(ctx, _cmd("diff", "doc-a", "doc-b"))
        assert "Relevância" not in r.text
        assert "Tier" not in r.text

    @pytest.mark.asyncio
    async def test_historico_doc_valido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_historico(ctx, _cmd("historico", "test-doc"))
        assert "Coletado" in r.text

    @pytest.mark.asyncio
    async def test_historico_sem_args(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_historico(ctx, _cmd("historico"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_historico_doc_id_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_historico(ctx, _cmd("historico", "a"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_historico_doc_inexistente(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_historico(ctx, _cmd("historico", "nao-existe"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_historico_sem_llm(self) -> None:
        ctx = await _ctx_with_doc(with_llm=False)
        r = await handle_historico(ctx, _cmd("historico", "test-doc"))
        assert "Coletado" in r.text
        assert "Classificado" not in r.text


@pytest.mark.unit
class TestComentarLembrarCancelar:
    @pytest.mark.asyncio
    async def test_comentar(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_comentar(ctx, _cmd("comentar", "test-doc", "isso é um teste"))
        assert "Comentário salvo" in r.text

    @pytest.mark.asyncio
    async def test_comentar_args_insuficientes(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_comentar(ctx, _cmd("comentar", "test-doc"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_comentar_doc_id_invalido(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_comentar(ctx, _cmd("comentar", "a", "texto"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_comentar_doc_inexistente(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_comentar(ctx, _cmd("comentar", "nao-existe", "texto"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_lembrar_data_valida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_lembrar(ctx, _cmd("lembrar", "revisar", "2026-12-31"))
        assert "Lembrete" in r.text

    @pytest.mark.asyncio
    async def test_lembrar_args_insuficientes(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_lembrar(ctx, _cmd("lembrar", "revisar"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_lembrar_data_invalida(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_lembrar(ctx, _cmd("lembrar", "revisar", "amanha"))
        assert r.is_error

    @pytest.mark.asyncio
    async def test_cancelar(self) -> None:
        ctx = await _ctx_with_doc()
        r = await handle_cancelar(ctx, _cmd("cancelar"))
        assert "expira" in r.text.lower() or "cancel" in r.text.lower()


@pytest.mark.unit
class TestSefazMG:
    """`/sefazmg [Nd]` — lista atos de fontes com `keywords_bypass=True`."""

    async def _ctx_with_bypass_doc(
        self,
        *,
        with_bypass: bool = True,
        published_at: datetime | None = None,
    ) -> BotContext:
        """Cria storage com 1 doc, fonte com ou sem keywords_bypass."""
        storage = InMemoryStorage(owner_id="o")
        src = Source(
            id="doe-mg" if with_bypass else "src-normal",
            uf="MG",
            nome="IOF/MG" if with_bypass else "Source Normal",
            tipo=TipoFonte.DOE,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
            keywords_bypass=with_bypass,
            org_mentions=["SEFAZ"] if with_bypass else None,
        )
        raw = RawItem(
            source_id=src.id,
            titulo_raw="PORTARIA SUFI Nº 99",
            url="https://x.gov.br/ato/99",
            fetched_at=published_at or NOW,
            data_publicacao=published_at or NOW,
            content_hash="a" * 64,
        )
        llm = LLMResult(
            classified_at=NOW,
            llm_model="x",
            llm_prompt_version="v1",
            tipo=TipoAto.PORTARIA,
            relevancia=7,
            severity_tier=SeverityTier.BAIXA,
            resumo="r",
        )
        doc = Documento(
            owner_id="o",
            doc_id="doc-99",
            source=src,
            original=raw,
            llm=llm,
            status=StatusDocumento.CLASSIFIED,
        )
        await storage.save_documento(doc)
        return BotContext(settings=_settings(), storage=storage, confirmation=TwoStepConfirmation())

    @pytest.mark.asyncio
    async def test_sem_args_usa_default_7d(self) -> None:
        ctx = await self._ctx_with_bypass_doc()
        r = await handle_sefazmg(ctx, _cmd("sefazmg"))
        assert not r.is_error
        assert "doe-mg" in r.text or "SEFAZ" in r.text.upper() or "fontes" in r.text

    @pytest.mark.asyncio
    async def test_arg_duration_valida(self) -> None:
        ctx = await self._ctx_with_bypass_doc()
        r = await handle_sefazmg(ctx, _cmd("sefazmg", "2w"))
        assert not r.is_error
        assert "2w" in r.text or "doe-mg" in r.text

    @pytest.mark.asyncio
    async def test_arg_invalida_retorna_erro(self) -> None:
        ctx = await self._ctx_with_bypass_doc()
        r = await handle_sefazmg(ctx, _cmd("sefazmg", "abc"))
        assert r.is_error
        assert "Formato inválido" in r.text or "invalido" in r.text.lower()

    @pytest.mark.asyncio
    async def test_fonte_sem_bypass_nao_aparece(self) -> None:
        """Doc de fonte normal (keywords_bypass=False) NÃO entra na listagem."""
        ctx = await self._ctx_with_bypass_doc(with_bypass=False)
        r = await handle_sefazmg(ctx, _cmd("sefazmg"))
        # Comando não retorna esse doc; deve dizer "Nenhum".
        assert "Nenhum" in r.text or "0 ato" in r.text

    @pytest.mark.asyncio
    async def test_doc_fora_da_janela_nao_aparece(self) -> None:
        """Doc publicado há 30 dias não aparece em /sefazmg 7d."""
        from datetime import timedelta  # noqa: PLC0415

        old_date = datetime.now(UTC) - timedelta(days=30)
        ctx = await self._ctx_with_bypass_doc(published_at=old_date)
        r = await handle_sefazmg(ctx, _cmd("sefazmg", "7d"))
        # Janela é 7d; doc tem 30d → não aparece.
        assert "Nenhum" in r.text or "0 ato" in r.text


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
            "sefazmg",
        ):
            assert cmd_name in HANDLERS, f"comando {cmd_name} não registrado"
