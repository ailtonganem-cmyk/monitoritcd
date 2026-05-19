"""Testes de integração do IOF/MG collector com httpx mockado via respx.

Cobre o fluxo completo:
1. POST Autenticar → JWT
2. GET ObterUltimaEdicaoECalendarioParaHome → caderno id
3. GET ObterEdicaoPorId/{id} → secoes
4. GET ObterArquivoCadernoPorId?id={id} → envelope com base64 do PDF
5. base64 decode + busca %PDF- → bytes do PDF
6. pypdf extract_text → texto
7. regex de atos + filtro por org_mentions → RawItems

Não acessa rede real — todos os endpoints são respondidos pelo respx.
"""

from __future__ import annotations

import base64

import httpx
import pytest
import respx

from monitoritcd.collectors import IOFMGCollector
from monitoritcd.core.base_collector import CollectorError, _DomainRateLimiter
from monitoritcd.core.models import Parser, Source, TipoFonte

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

# JWT fictício; o coletor só passa adiante, não decodifica.
_FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.fake.signature"

# PDF mínimo válido com 1 página contendo cabeçalhos de atos. Construído à
# mão para garantir extract_text() retorna texto exato.
_FAKE_PDF: bytes = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n"
    b"2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n"
    b"3 0 obj\n"
    b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
    b"/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>\n"
    b"endobj\n"
    b"4 0 obj\n<</Length 350>>stream\n"
    b"BT /F1 12 Tf 50 700 Td "
    b"(PORTARIA SUFI No 99, DE 18 DE MAIO DE 2026) Tj T* "
    b"(Designa servidor para funcao de fiscal da SEFAZ.) Tj T* "
    b"(PORTARIA No 100, DE 18 DE MAIO DE 2026) Tj T* "
    b"(Nomeacao de cargo na Secretaria de Estado de Fazenda.) Tj T* "
    b"(PORTARIA No 555, DE 18 DE MAIO DE 2026) Tj T* "
    b"(Designa delegado titular. Sem relacao com tributo.) Tj "
    b"ET\nendstream\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n"
    b"0000000056 00000 n\n0000000101 00000 n\n0000000230 00000 n\n"
    b"trailer\n<</Size 5/Root 1 0 R>>\nstartxref\n600\n%%EOF\n"
)

# Envelope = PDF com prefixo PKCS#7 binário simulado.
_FAKE_ENVELOPE: bytes = b"\x30\x80\x06\x09" + b"\x00" * 50 + _FAKE_PDF + b"\x00" * 20
_FAKE_PDF_B64: str = base64.b64encode(_FAKE_ENVELOPE).decode("ascii")


def _iof_source(
    *,
    keywords_bypass: bool = True,
    org_mentions: list[str] | None = None,
) -> Source:
    return Source(
        id="doe-mg",
        uf="MG",
        nome="IOF/MG",
        tipo=TipoFonte.DOE,
        parser=Parser.IOF_MG,
        url="https://www.jornalminasgerais.mg.gov.br/",
        keywords_bypass=keywords_bypass,
        org_mentions=org_mentions or ["SEFAZ", "Secretaria de Estado de Fazenda"],
    )


def _mock_auth(router: respx.Router, *, success: bool = True) -> None:
    url = "https://www.jornalminasgerais.mg.gov.br/api/v1/Autenticacao/Autenticar"
    if success:
        router.post(url).mock(
            return_value=httpx.Response(200, json={"dados": _FAKE_JWT, "erros": []}),
        )
    else:
        router.post(url).mock(
            return_value=httpx.Response(500, json={"erros": ["unavailable"]}),
        )


def _mock_home(router: respx.Router, caderno_id: int = 329501) -> None:
    router.get(
        "https://www.jornalminasgerais.mg.gov.br/api/v1/Jornal/ObterUltimaEdicaoECalendarioParaHome"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "dados": {
                    "dataPublicacaoUltimaEdicao": "2026-05-19T00:00:00",
                    "cadernosUltimaEdicao": [
                        {"id": caderno_id, "descricao": "Diário do Executivo", "ordem": 100},
                        {
                            "id": caderno_id + 1,
                            "descricao": "Diário dos Municípios Mineiros",
                            "ordem": 200,
                        },
                    ],
                    "edicoesCalendario": [],
                },
                "erros": [],
            },
        ),
    )


def _mock_edicao_detail(router: respx.Router, caderno_id: int = 329501) -> None:
    router.get(
        f"https://www.jornalminasgerais.mg.gov.br/api/v1/Jornal/ObterEdicaoPorId/{caderno_id}"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "dados": {
                    "dataPublicacao": "2026-05-19T00:00:00",
                    "cadernos": [
                        {
                            "id": caderno_id,
                            "descricao": "Diário do Executivo",
                            "ordem": 100,
                            "secoes": [
                                {"descricao": "Governo do Estado", "paginaInicial": 1},
                                {
                                    "descricao": "Secretaria de Estado de Fazenda",
                                    "paginaInicial": 27,
                                },
                            ],
                        }
                    ],
                },
                "erros": [],
            },
        ),
    )


def _mock_pdf(
    router: respx.Router, caderno_id: int = 329501, *, payload: dict | None = None
) -> None:
    router.get(
        f"https://www.jornalminasgerais.mg.gov.br/api/v1/Caderno/ObterArquivoCadernoPorId?id={caderno_id}"
    ).mock(
        return_value=httpx.Response(
            200,
            json=payload
            if payload is not None
            else {"dados": {"arquivo": _FAKE_PDF_B64}, "erros": []},
        ),
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    _DomainRateLimiter._reset_for_tests()


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestHappyPath:
    @pytest.mark.asyncio
    async def test_collects_acts_mentioning_sefaz_only(self) -> None:
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            _mock_home(router)
            _mock_edicao_detail(router)
            _mock_pdf(router)

            async with IOFMGCollector(_iof_source()) as c:
                items = await c.collect()

        # 3 atos no PDF; 2 mencionam SEFAZ-MG, 1 (PORTARIA 555) não.
        assert len(items) == 2
        titulos = [it.titulo_raw for it in items]
        # PORTARIA SUFI 99 e PORTARIA 100 (ambos com SEFAZ).
        assert any("99" in t for t in titulos)
        assert any("100" in t for t in titulos)
        assert not any("555" in t for t in titulos)

    @pytest.mark.asyncio
    async def test_items_have_url_deeplink_with_caderno_id(self) -> None:
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            _mock_home(router, caderno_id=329501)
            _mock_edicao_detail(router, caderno_id=329501)
            _mock_pdf(router, caderno_id=329501)
            async with IOFMGCollector(_iof_source()) as c:
                items = await c.collect()
        # URL deeplink contém idCadernoEdicaoSelecionado urlencoded.
        assert any("329501" in it.url for it in items)
        assert all(it.url.startswith("https://www.jornalminasgerais.mg.gov.br/") for it in items)

    @pytest.mark.asyncio
    async def test_items_have_data_publicacao(self) -> None:
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            _mock_home(router)
            _mock_edicao_detail(router)
            _mock_pdf(router)
            async with IOFMGCollector(_iof_source()) as c:
                items = await c.collect()
        for it in items:
            assert it.data_publicacao is not None
            assert it.data_publicacao.year == 2026
            assert it.data_publicacao.month == 5


# ─────────────────────────────────────────────────────────────────────────────
# Erros do pipeline
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestErrorPaths:
    @pytest.mark.asyncio
    async def test_auth_failure_raises_collector_error(self) -> None:
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router, success=False)
            with pytest.raises(CollectorError) as exc:
                async with IOFMGCollector(_iof_source()) as c:
                    await c.collect()
            assert "auth falhou" in str(exc.value)

    @pytest.mark.asyncio
    async def test_auth_returns_payload_without_dados_raises(self) -> None:
        async with respx.mock(assert_all_called=False) as router:
            router.post(
                "https://www.jornalminasgerais.mg.gov.br/api/v1/Autenticacao/Autenticar"
            ).mock(return_value=httpx.Response(200, json={"erros": ["x"]}))
            with pytest.raises(CollectorError) as exc:
                async with IOFMGCollector(_iof_source()) as c:
                    await c.collect()
            assert "sem 'dados'" in str(exc.value)

    @pytest.mark.asyncio
    async def test_caderno_not_found_raises(self) -> None:
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            # Home não traz "Diário do Executivo".
            router.get(
                "https://www.jornalminasgerais.mg.gov.br/api/v1/Jornal/ObterUltimaEdicaoECalendarioParaHome"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "dados": {
                            "dataPublicacaoUltimaEdicao": "2026-05-19T00:00:00",
                            "cadernosUltimaEdicao": [
                                {"id": 9999, "descricao": "Outro Caderno", "ordem": 100},
                            ],
                            "edicoesCalendario": [],
                        }
                    },
                ),
            )
            with pytest.raises(CollectorError) as exc:
                async with IOFMGCollector(_iof_source()) as c:
                    await c.collect()
            assert "Diário do Executivo" in str(exc.value)

    @pytest.mark.asyncio
    async def test_pdf_endpoint_without_arquivo_field_raises(self) -> None:
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            _mock_home(router)
            _mock_edicao_detail(router)
            _mock_pdf(router, payload={"dados": {}, "erros": []})
            with pytest.raises(CollectorError) as exc:
                async with IOFMGCollector(_iof_source()) as c:
                    await c.collect()
            assert "sem campo 'arquivo'" in str(exc.value)

    @pytest.mark.asyncio
    async def test_invalid_base64_raises(self) -> None:
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            _mock_home(router)
            _mock_edicao_detail(router)
            _mock_pdf(
                router,
                payload={"dados": {"arquivo": "@@@not-valid-base64!@@@"}, "erros": []},
            )
            with pytest.raises(CollectorError) as exc:
                async with IOFMGCollector(_iof_source()) as c:
                    await c.collect()
            assert "base64" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_envelope_without_pdf_magic_raises(self) -> None:
        envelope = b"\x30\x80" + b"\x00" * 100  # PKCS#7-looking sem PDF dentro
        b64 = base64.b64encode(envelope).decode("ascii")
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            _mock_home(router)
            _mock_edicao_detail(router)
            _mock_pdf(router, payload={"dados": {"arquivo": b64}, "erros": []})
            with pytest.raises(CollectorError) as exc:
                async with IOFMGCollector(_iof_source()) as c:
                    await c.collect()
            assert "%PDF-" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# Filtragem e seleção de caderno
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestSelectorBehavior:
    @pytest.mark.asyncio
    async def test_caderno_alvo_configurable_via_selectors(self) -> None:
        """Source.selectors.caderno permite trocar para Municípios Mineiros."""
        src = _iof_source()
        # Reconstrói com selector trocado (Source é frozen).
        src = Source(
            id=src.id,
            uf=src.uf,
            nome=src.nome,
            tipo=src.tipo,
            parser=src.parser,
            url=src.url,
            keywords_bypass=src.keywords_bypass,
            org_mentions=src.org_mentions,
            selectors={"caderno": "Diário dos Municípios Mineiros"},
        )
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            _mock_home(router, caderno_id=329501)  # Municípios será id 329502
            _mock_edicao_detail(router, caderno_id=329502)
            _mock_pdf(router, caderno_id=329502)
            async with IOFMGCollector(src) as c:
                items = await c.collect()
        # PDF tem 2 atos com SEFAZ.
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_no_org_mentions_filter_lets_orchestrator_handle(self) -> None:
        """Sem org_mentions e sem keywords_required, todos os atos passam pro orquestrador."""
        src = Source(
            id="iof-no-filter",
            uf="MG",
            nome="IOF no filter",
            tipo=TipoFonte.DOE,
            parser=Parser.IOF_MG,
            url="https://www.jornalminasgerais.mg.gov.br/",
            keywords_bypass=False,  # validador exige org_mentions se bypass=True
            org_mentions=None,
            keywords_required=[],
        )
        async with respx.mock(assert_all_called=False) as router:
            _mock_auth(router)
            _mock_home(router)
            _mock_edicao_detail(router)
            _mock_pdf(router)
            async with IOFMGCollector(src) as c:
                items = await c.collect()
        # 3 atos: SUFI 99, 100, 555 — todos passam pq collector não filtra localmente.
        assert len(items) == 3
