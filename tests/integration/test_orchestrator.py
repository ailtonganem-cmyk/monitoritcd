"""Testes E2E do orquestrador (com fakes — sem rede real).

Cobre:
- Pipeline completa: collect → filter → classify → store
- Filtragem por active_states (federal_active + active_uf)
- Falhas isoladas em fontes não derrubam pipeline
- Healthcheck silencioso (best-effort)
- Audit log gravado
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — usado em runtime no fixture
from textwrap import dedent

import pytest
from pydantic import SecretStr

from monitoritcd.core.config import Settings
from monitoritcd.core.models import ActiveStatesConfig
from monitoritcd.llm.fake import FakeLLMProvider
from monitoritcd.orchestrator import (
    RunReport,
    classify_and_store,
    filter_by_dedup,
    filter_by_keywords,
    filter_by_prescore,
    make_collector,
    ping_healthcheck,
    run_pipeline,
)
from monitoritcd.storage import InMemoryStorage

NOW = datetime(2026, 4, 24, tzinfo=UTC)
OWNER = "owner-test"


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
        HEALTHCHECKS_URL=None,
    )


def _write_yaml(path: Path, content: str) -> Path:
    path.write_text(dedent(content), encoding="utf-8")
    return path


@pytest.fixture
def sources_dir(tmp_path: Path) -> Path:
    fed_dir = tmp_path / "_federal"
    sp_dir = tmp_path / "SP"
    mg_dir = tmp_path / "MG"
    fed_dir.mkdir()
    sp_dir.mkdir()
    mg_dir.mkdir()

    # Source federal — RSS dummy via httpx-mock pattern via collector real
    _write_yaml(
        fed_dir / "fake-fed.yaml",
        """\
        id: fake-fed
        uf: _federal
        nome: "Fake Federal"
        tipo: noticia
        parser: generic_rss
        url: "https://www.example.gov.br/feed.xml"
        keywords_required:
          - ITCMD
        ativo: true
        """,
    )
    _write_yaml(
        sp_dir / "fake-sp.yaml",
        """\
        id: fake-sp
        uf: SP
        nome: "Fake SP"
        tipo: sefaz
        parser: generic_rss
        url: "https://www.example.gov.br/feed-sp.xml"
        keywords_required:
          - ITCMD
        ativo: true
        """,
    )
    _write_yaml(
        mg_dir / "fake-mg-geo.yaml",
        """\
        id: fake-mg-geo
        uf: MG
        nome: "Fake MG geo-restricted"
        tipo: assembleia
        parser: generic_rss
        url: "https://www.example.gov.br/feed-mg.xml"
        keywords_required:
          - ITCMD
        ativo: true
        geo_restricted: true
        """,
    )
    return tmp_path


@pytest.mark.integration
class TestMakeCollector:
    def test_lexml_parser(self) -> None:
        from monitoritcd.core.models import Parser, Source, TipoFonte  # noqa: PLC0415

        src = Source(
            id="x",
            uf="_federal",
            nome="x",
            tipo=TipoFonte.JURISPRUDENCIA,
            parser=Parser.LEXML,
            url="https://www.lexml.gov.br/",
        )
        collector = make_collector(src)
        assert collector.source.id == "x"


@pytest.mark.integration
class TestFilterFunctions:
    def test_filter_by_keywords(self) -> None:
        from monitoritcd.core.models import Parser, RawItem, Source, TipoFonte  # noqa: PLC0415

        src = Source(
            id="s",
            uf="SP",
            nome="x",
            tipo=TipoFonte.SEFAZ,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        items = [
            (
                src,
                RawItem(
                    source_id="s",
                    titulo_raw="Notícia sobre ITCMD em SP",
                    url="https://x.gov.br/1",
                    fetched_at=NOW,
                    content_hash="a" * 64,
                ),
            ),
            (
                src,
                RawItem(
                    source_id="s",
                    titulo_raw="Notícia sobre futebol",
                    url="https://x.gov.br/2",
                    fetched_at=NOW,
                    content_hash="b" * 64,
                ),
            ),
        ]
        result = filter_by_keywords(items)
        assert len(result) == 1
        assert "ITCMD" in result[0][1].titulo_raw

    def test_filter_by_prescore(self) -> None:
        from monitoritcd.core.models import Parser, RawItem, Source, TipoFonte  # noqa: PLC0415

        src = Source(
            id="s",
            uf="SP",
            nome="x",
            tipo=TipoFonte.SEFAZ,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
            trusted=True,
        )
        items = [
            (
                src,
                RawItem(
                    source_id="s",
                    titulo_raw="ITCMD progressivo",
                    url="https://x.gov.br/",
                    fetched_at=NOW,
                    data_publicacao=NOW,
                    content_hash="a" * 64,
                ),
                ["ITCMD"],
            ),
        ]
        result = filter_by_prescore(items)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_filter_by_dedup(self) -> None:
        from monitoritcd.core.models import (  # noqa: PLC0415
            Documento,
            Parser,
            RawItem,
            Source,
            StatusDocumento,
            TipoFonte,
        )

        storage = InMemoryStorage(OWNER)
        src = Source(
            id="s",
            uf="SP",
            nome="x",
            tipo=TipoFonte.SEFAZ,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        existing_hash = "a" * 64
        # Salva um doc primeiro
        existing_raw = RawItem(
            source_id="s",
            titulo_raw="x",
            url="https://x.gov.br/",
            fetched_at=NOW,
            content_hash=existing_hash,
        )
        await storage.save_documento(
            Documento(
                owner_id=OWNER,
                doc_id="exists",
                source=src,
                original=existing_raw,
                status=StatusDocumento.PENDING,
            ),
        )

        # Tenta filtrar 2 items, um já existe
        items = [
            (src, existing_raw),
            (
                src,
                RawItem(
                    source_id="s",
                    titulo_raw="novo",
                    url="https://x.gov.br/n",
                    fetched_at=NOW,
                    content_hash="b" * 64,
                ),
            ),
        ]
        result = await filter_by_dedup(items, storage)
        assert len(result) == 1
        assert result[0][1].content_hash == "b" * 64


@pytest.mark.integration
class TestClassifyAndStore:
    @pytest.mark.asyncio
    async def test_classifies_and_saves(self) -> None:
        from monitoritcd.core.models import Parser, RawItem, Source, TipoFonte  # noqa: PLC0415

        storage = InMemoryStorage(OWNER)
        src = Source(
            id="s",
            uf="SP",
            nome="x",
            tipo=TipoFonte.SEFAZ,
            parser=Parser.GENERIC_HTML,
            url="https://x.gov.br/",
        )
        item = RawItem(
            source_id="s",
            titulo_raw="ITCMD progressivo SP",
            url="https://x.gov.br/i",
            fetched_at=NOW,
            content_hash="a" * 64,
        )
        report = RunReport(run_id="t", started_at=NOW)
        docs = await classify_and_store(
            [(src, item)],
            llm_provider=FakeLLMProvider(),
            storage=storage,
            owner_id=OWNER,
            report=report,
        )
        assert len(docs) == 1
        assert docs[0].llm is not None
        assert report.items_stored == 1


@pytest.mark.integration
class TestRunPipeline:
    @pytest.mark.asyncio
    async def test_no_active_uf_only_federal(
        self,
        sources_dir: Path,
    ) -> None:
        # Sem active_states → federal default ativo, mas SP não está em active_uf
        # → fonte SP é skipada
        storage = InMemoryStorage(OWNER)

        # Mocka httpx para ambos URLs (fonte real chamaria rede senão)
        import respx  # noqa: PLC0415

        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=__import__("httpx").Response(200, text=_minimal_rss("fed")),
            )
            respx.get("https://www.example.gov.br/feed-sp.xml").mock(
                return_value=__import__("httpx").Response(200, text=_minimal_rss("sp")),
            )

            report = await run_pipeline(
                _settings(),
                storage=storage,
                llm_provider=FakeLLMProvider(),
                sources_dir=sources_dir,
            )
        # Apenas federal coletado (SP não está em active_uf, federal_active default True)
        assert report.sources_consulted == 1

    @pytest.mark.asyncio
    async def test_with_active_states_includes_sp(
        self,
        sources_dir: Path,
    ) -> None:
        storage = InMemoryStorage(OWNER)
        await storage.save_active_states(
            ActiveStatesConfig(
                owner_id=OWNER,
                active_uf=["SP"],
                federal_active=True,
                updated_at=NOW,
                updated_by="test",
            ),
        )

        import respx  # noqa: PLC0415

        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=__import__("httpx").Response(200, text=_minimal_rss("fed")),
            )
            respx.get("https://www.example.gov.br/feed-sp.xml").mock(
                return_value=__import__("httpx").Response(200, text=_minimal_rss("sp")),
            )

            report = await run_pipeline(
                _settings(),
                storage=storage,
                llm_provider=FakeLLMProvider(),
                sources_dir=sources_dir,
            )

        assert report.sources_consulted == 2  # fed + SP
        assert report.items_stored >= 1

    @pytest.mark.asyncio
    async def test_isolated_failure_per_source(self, sources_dir: Path) -> None:
        storage = InMemoryStorage(OWNER)
        await storage.save_active_states(
            ActiveStatesConfig(
                owner_id=OWNER,
                active_uf=["SP"],
                federal_active=True,
                updated_at=NOW,
                updated_by="test",
            ),
        )

        import httpx  # noqa: PLC0415
        import respx  # noqa: PLC0415

        async with respx.mock:
            # Federal funciona; SP falha 500
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=httpx.Response(200, text=_minimal_rss("fed")),
            )
            respx.get("https://www.example.gov.br/feed-sp.xml").mock(
                return_value=httpx.Response(500),
            )

            report = await run_pipeline(
                _settings(),
                storage=storage,
                llm_provider=FakeLLMProvider(),
                sources_dir=sources_dir,
            )

        assert report.sources_consulted == 2
        assert report.sources_failed == 1
        assert "fake-sp" in report.failed_sources

    @pytest.mark.asyncio
    async def test_skip_geo_restricted(self, sources_dir: Path) -> None:
        import httpx  # noqa: PLC0415
        import respx  # noqa: PLC0415

        # active_uf inclui MG e SP; --skip-geo-restricted deve excluir só MG (geo_restricted=true)
        storage = InMemoryStorage(OWNER)
        await storage.save_active_states(
            ActiveStatesConfig(
                owner_id=OWNER,
                active_uf=["MG", "SP"],
                federal_active=True,
                updated_at=NOW,
                updated_by="test",
            ),
        )
        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=httpx.Response(200, text=_minimal_rss("fed")),
            )
            respx.get("https://www.example.gov.br/feed-sp.xml").mock(
                return_value=httpx.Response(200, text=_minimal_rss("sp")),
            )
            report = await run_pipeline(
                _settings(),
                storage=storage,
                llm_provider=FakeLLMProvider(),
                sources_dir=sources_dir,
                skip_geo_restricted=True,
            )
        # 2 = federal + SP (MG excluida por geo_restricted)
        assert report.sources_consulted == 2

    @pytest.mark.asyncio
    async def test_only_geo_restricted(self, sources_dir: Path) -> None:
        import httpx  # noqa: PLC0415
        import respx  # noqa: PLC0415

        # only_geo_restricted=True: apenas MG roda; federal e SP são puladas
        storage = InMemoryStorage(OWNER)
        await storage.save_active_states(
            ActiveStatesConfig(
                owner_id=OWNER,
                active_uf=["MG", "SP"],
                federal_active=True,
                updated_at=NOW,
                updated_by="test",
            ),
        )
        async with respx.mock:
            respx.get("https://www.example.gov.br/feed-mg.xml").mock(
                return_value=httpx.Response(200, text=_minimal_rss("mg")),
            )
            report = await run_pipeline(
                _settings(),
                storage=storage,
                llm_provider=FakeLLMProvider(),
                sources_dir=sources_dir,
                only_geo_restricted=True,
            )
        # Apenas MG (geo_restricted=true)
        assert report.sources_consulted == 1

    @pytest.mark.asyncio
    async def test_filter_by_only_source_id(self, sources_dir: Path) -> None:
        storage = InMemoryStorage(OWNER)
        await storage.save_active_states(
            ActiveStatesConfig(
                owner_id=OWNER,
                active_uf=["SP"],
                federal_active=True,
                updated_at=NOW,
                updated_by="test",
            ),
        )

        import httpx  # noqa: PLC0415
        import respx  # noqa: PLC0415

        async with respx.mock:
            respx.get("https://www.example.gov.br/feed.xml").mock(
                return_value=httpx.Response(200, text=_minimal_rss("fed")),
            )

            report = await run_pipeline(
                _settings(),
                storage=storage,
                llm_provider=FakeLLMProvider(),
                sources_dir=sources_dir,
                only_source_id="fake-fed",
            )

        assert report.sources_consulted == 1


@pytest.mark.integration
class TestHealthcheck:
    @pytest.mark.asyncio
    async def test_no_url_is_silent(self) -> None:
        # HEALTHCHECKS_URL=None → não faz nada
        s = _settings()
        await ping_healthcheck(s, success=True)  # não levanta

    @pytest.mark.asyncio
    async def test_with_url_does_request(self) -> None:
        import httpx  # noqa: PLC0415
        import respx  # noqa: PLC0415
        from pydantic import HttpUrl  # noqa: PLC0415

        s = _settings()
        url = "https://hc-ping.com/abc-def"
        s2 = s.model_copy(update={"HEALTHCHECKS_URL": HttpUrl(url)})

        async with respx.mock:
            route = respx.get(url).mock(return_value=httpx.Response(200))
            await ping_healthcheck(s2, success=True)
            assert route.called

    @pytest.mark.asyncio
    async def test_failure_uses_fail_endpoint(self) -> None:
        import httpx  # noqa: PLC0415
        import respx  # noqa: PLC0415
        from pydantic import HttpUrl  # noqa: PLC0415

        s = _settings()
        url = "https://hc-ping.com/abc-def"
        s2 = s.model_copy(update={"HEALTHCHECKS_URL": HttpUrl(url)})

        async with respx.mock:
            route_fail = respx.get(url + "/fail").mock(return_value=httpx.Response(200))
            await ping_healthcheck(s2, success=False)
            assert route_fail.called


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _minimal_rss(prefix: str) -> str:
    """Gera RSS mínimo com 2 itens contendo ITCMD."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Test</title>
  <link>https://x.gov.br/</link>
  <description>x</description>
  <item>
    <title>{prefix} — ITCMD em SP progressivo</title>
    <link>https://x.gov.br/{prefix}/1</link>
    <pubDate>Mon, 22 Apr 2026 10:00:00 -0300</pubDate>
    <description>Detalhes sobre ITCMD em SP.</description>
  </item>
  <item>
    <title>{prefix} — IN sobre ITCMD doação</title>
    <link>https://x.gov.br/{prefix}/2</link>
    <pubDate>Tue, 23 Apr 2026 10:00:00 -0300</pubDate>
    <description>IN nova de SEFAZ sobre ITCMD doação.</description>
  </item>
</channel></rss>
"""
