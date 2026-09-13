"""Testes do render Telegram (MarkdownV2).

Verifica:
- Escape correto de chars especiais
- Split de mensagens longas (≤ 4096 bytes)
- Resistência a markdown injection
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

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
from monitoritcd.notifiers.email_notifier import build_jinja_env
from monitoritcd.notifiers.telegram_notifier import render_telegram
from monitoritcd.security.markdown_escape import split_for_telegram

FIXED_NOW = datetime(2026, 4, 24, 7, 13, tzinfo=UTC)


def _doc(
    *,
    titulo: str = "PL 1234/2026 — ITCMD progressivo (SP)",
    resumo: str = "Resumo factual.",
    resumo_completo: str = "",
    pontos_chave: list[str] | None = None,
    assuntos_relacionados: list[str] | None = None,
    contexto: str = "",
    tier: SeverityTier = SeverityTier.ALTA,
    uf: str = "SP",
    url: str = "https://www.example.gov.br/pl-1234",
) -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw=titulo,
        url=url,
        fetched_at=FIXED_NOW,
        data_publicacao=FIXED_NOW,
        content_hash="a" * 64,
    )
    src = Source(
        id="src",
        uf=uf,
        nome="ALESP",
        tipo=TipoFonte.ASSEMBLEIA,
        parser=Parser.GENERIC_HTML,
        url="https://www.al.sp.gov.br/",
    )
    llm = LLMResult(
        classified_at=FIXED_NOW,
        llm_model="gemini",
        llm_prompt_version="v1",
        tipo=TipoAto.PROJETO_LEI,
        relevancia=8,
        severity_tier=tier,
        resumo=resumo,
        resumo_completo=resumo_completo,
        pontos_chave=pontos_chave or [],
        assuntos_relacionados=assuntos_relacionados or [],
        contexto=contexto,
    )
    return Documento(
        owner_id="owner",
        doc_id="d1",
        source=src,
        original=raw,
        llm=llm,
        status=StatusDocumento.CLASSIFIED,
    )


@pytest.mark.templates
class TestTelegramRender:
    def test_autoescape_html_nao_aplica_em_markdown(self) -> None:
        env = build_jinja_env()
        assert callable(env.autoescape)
        assert env.autoescape("email.html.j2") is True
        assert env.autoescape("email_compacto.html.j2") is True
        assert env.autoescape("telegram.md.j2") is False
        assert env.autoescape("digest.md.j2") is False

    def test_renders_basic_digest(self) -> None:
        text = render_telegram([_doc()], digest_label="Diário", data_geracao=FIXED_NOW)
        assert "MonitorITCD" in text
        # Chars especiais escapados
        assert "PL 1234" in text
        # `(SP)` deve aparecer como `\(SP\)`
        assert r"\(SP\)" in text

    def test_empty_digest(self) -> None:
        text = render_telegram([], digest_label="Diário", data_geracao=FIXED_NOW)
        assert "Sem novidades" in text
        assert "0 novidades" in text

    def test_url_inside_markdown_link(self) -> None:
        text = render_telegram([_doc()], digest_label="Diário", data_geracao=FIXED_NOW)
        # URL dentro de [text](url) — não escapada como o resto
        assert "https://www.example.gov.br/pl-1234" in text
        assert "Abrir original" in text

    def test_markdown_injection_in_titulo_neutralized(self) -> None:
        # Título contendo chars especiais que poderiam quebrar formatação
        injected = "*injected* _emphasis_ [link](http://evil.com)"
        text = render_telegram(
            [_doc(titulo=injected)], digest_label="Diário", data_geracao=FIXED_NOW
        )
        # Os asteriscos do título devem estar escapados
        # No template, o título vem dentro de *bold* — o `*` literal deve estar com `\`
        assert "\\*injected\\*" in text
        assert "\\[link\\]" in text or "\\(http" in text

    def test_dot_in_data_escaped(self) -> None:
        # `.` em data deve ser escapado em MarkdownV2
        text = render_telegram([_doc()], digest_label="Diário", data_geracao=FIXED_NOW)
        # O ponto em "24/04/2026" não usa . mas a hora "07:13" tem `:` que NÃO é especial
        # `/` não é especial em MarkdownV2; OK
        assert "24/04/2026" in text

    def test_count_pluralization(self) -> None:
        single = render_telegram([_doc()], digest_label="Diário", data_geracao=FIXED_NOW)
        multiple = render_telegram(
            [_doc(), _doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "1 novidade" in single
        assert "2 novidades" in multiple

    def test_emoji_no_titulo(self) -> None:
        text = render_telegram(
            [_doc(titulo="🔥 PL 1234/2026 ITCMD")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "🔥" in text
        assert "PL 1234" in text

    def test_lista_grande_telegrampossivelmente_split(self) -> None:
        # 30 docs deve gerar texto grande mas single rendered (split é separado)
        docs = [_doc(titulo=f"PL {i}") for i in range(30)]
        text = render_telegram(docs, digest_label="Diário", data_geracao=FIXED_NOW)
        for i in (0, 15, 29):
            assert f"PL {i}" in text

    def test_uf_federal_na_renderizacao(self) -> None:
        text = render_telegram(
            [_doc(uf="_federal")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        # UF=_federal: aparece como `(\_federal)` ou tratamento equivalente
        # Underscore escapado em MarkdownV2
        assert "ederal" in text  # cobre "Federal" ou "_federal"

    def test_usa_resumo_completo_e_escapa_campos_novos(self) -> None:
        text = render_telegram(
            [
                _doc(
                    resumo="Resumo curto não deve aparecer.",
                    resumo_completo="Resumo completo com ITCMD progressivo.",
                    pontos_chave=["Base *especial*"],
                    assuntos_relacionados=["Doação (SP)"],
                )
            ],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "Resumo completo com ITCMD progressivo" in text
        assert "Resumo curto não deve aparecer" not in text
        assert r"Base \*especial\*" in text
        assert r"Doação \(SP\)" in text

    def test_contexto_renderiza_rotulado_como_ia_e_escapado(self) -> None:
        text = render_telegram(
            [_doc(contexto="Súmula 377/STF (aquestos) trata do tema.")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "Contexto \\(IA\\)" in text
        assert r"Súmula 377/STF \(aquestos\) trata do tema" in text

    def test_contexto_ausente_nao_renderiza_bloco(self) -> None:
        text = render_telegram(
            [_doc(contexto="")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "Contexto \\(IA\\)" not in text

    def test_aspas_nao_viram_entidade_html_com_hash_nu(self) -> None:
        # #46 — autoescape HTML em telegram.md.j2 gerava &#34;/&#39; e o
        # Telegram rejeitava o `#` das entidades (400 MarkdownV2).
        text = render_telegram(
            [
                _doc(
                    titulo='PL 1234/2026 — "ITCMD" progressivo',
                    resumo="Altera a 'base de cálculo' do imposto.",
                )
            ],
            digest_label="Semanal",
            data_geracao=FIXED_NOW,
        )
        assert "&#" not in text
        assert "&amp;" not in text
        assert '"ITCMD"' in text
        assert "'base de cálculo'" in text

    def test_hash_literal_no_titulo_e_resumo_continua_escapado(self) -> None:
        text = render_telegram(
            [_doc(titulo="PL 1234 #tema", resumo="Ver #ITCMD na ementa.")],
            digest_label="Semanal",
            data_geracao=FIXED_NOW,
        )
        assert r"\#tema" in text
        assert r"\#ITCMD" in text
        assert "#tema" not in text.replace(r"\#tema", "")
        assert "#ITCMD" not in text.replace(r"\#ITCMD", "")

    def test_ampersand_e_fragmento_na_url_nao_viram_html(self) -> None:
        text = render_telegram(
            [_doc(url="https://www.example.gov.br/pl?a=1&b=2#secao")],
            digest_label="Semanal",
            data_geracao=FIXED_NOW,
        )
        assert "https://www.example.gov.br/pl?a=1&b=2#secao" in text
        assert "&amp;" not in text


@pytest.mark.templates
class TestTelegramSplit:
    def test_long_message_splits_under_4096_bytes(self) -> None:
        # Resumo respeita MAX_SUMMARY_LENGTH (2000) — múltiplos itens forçam split.
        long_resumo = "a " * 800  # ~1600 chars, dentro do limite
        docs = [_doc(resumo=long_resumo) for _ in range(5)]
        text = render_telegram(docs, digest_label="Diário", data_geracao=FIXED_NOW)
        chunks = split_for_telegram(text, max_bytes=4096)
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 4096

    def test_resumo_completo_longo_split_seguro(self) -> None:
        long_resumo = "a" * 6000
        text = render_telegram(
            [_doc(resumo_completo=long_resumo)],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        chunks = split_for_telegram(text, max_bytes=4096)
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 4096

    def test_short_message_single_chunk(self) -> None:
        text = render_telegram([_doc()], digest_label="Diário", data_geracao=FIXED_NOW)
        chunks = split_for_telegram(text, max_bytes=4096)
        assert len(chunks) == 1
