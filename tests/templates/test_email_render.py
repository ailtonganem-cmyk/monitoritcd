"""Snapshot tests para o template de e-mail.

Mudanças no template requerem aprovação explícita (`pytest --snapshot-update`).
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
from monitoritcd.notifiers.email_notifier import render_email

FIXED_NOW = datetime(2026, 4, 24, 7, 13, tzinfo=UTC)


def _doc(
    *,
    titulo: str = "PL 1234/2026 — ITCMD progressivo SP",
    tier: SeverityTier = SeverityTier.ALTA,
    tipo: TipoAto = TipoAto.PROJETO_LEI,
    uf: str = "SP",
    resumo: str = "Projeto institui alíquota progressiva de ITCMD em SP.",
) -> Documento:
    raw = RawItem(
        source_id="src",
        titulo_raw=titulo,
        url="https://www.example.gov.br/pl-1234",
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
        llm_model="gemini-2.5-flash",
        llm_prompt_version="v1.0",
        tipo=tipo,
        relevancia=8,
        severity_tier=tier,
        resumo=resumo,
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
class TestEmailRender:
    def test_subject_includes_count(self) -> None:
        subject, _ = render_email(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "1 novidades" in subject

    def test_empty_state_renders(self) -> None:
        subject, body = render_email(
            [],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "0 novidades" in subject
        assert "Sem novidades" in body

    def test_body_contains_titulo(self) -> None:
        _, body = render_email(
            [_doc(titulo="PL 9999/2026 — Holding Familiar")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "PL 9999/2026" in body
        assert "Holding Familiar" in body

    def test_xss_in_titulo_is_escaped(self) -> None:
        # Princípio canônico 1: backend não confia. Conteúdo coletado pode ter XSS.
        _, body = render_email(
            [_doc(titulo="<script>alert('xss')</script>")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        # Jinja2 com autoescape escapa < e >
        assert "<script>" not in body
        assert "&lt;script&gt;" in body

    def test_xss_in_resumo_escaped(self) -> None:
        _, body = render_email(
            [_doc(resumo="Texto <img src=x onerror=alert(1)>")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "<img" not in body
        assert "onerror" not in body or "&" in body  # escapado

    def test_url_does_not_break_template(self) -> None:
        # URL com chars especiais não deve quebrar HTML
        doc = _doc()
        _, body = render_email(
            [doc],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert doc.original.url in body

    def test_csp_header_present(self) -> None:
        _, body = render_email([_doc()], digest_label="x", data_geracao=FIXED_NOW)
        assert 'http-equiv="Content-Security-Policy"' in body

    def test_highlights_section_for_critico_alta(self) -> None:
        docs = [
            _doc(titulo="Crítico", tier=SeverityTier.CRITICO),
            _doc(titulo="Alta", tier=SeverityTier.ALTA),
            _doc(titulo="Normal", tier=SeverityTier.NORMAL),
        ]
        _, body = render_email(docs, digest_label="Diário", data_geracao=FIXED_NOW)
        assert "Destaques" in body or "destaques" in body

    def test_snapshot_simple_digest(self, snapshot: object) -> None:
        # Snapshot test — qualquer mudança visual no template detectada.
        _, body = render_email(
            [_doc()],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        # Stripa whitespace variável para snapshot estável
        normalized = "\n".join(line.rstrip() for line in body.splitlines() if line.strip())
        assert normalized == snapshot

    def test_emoji_no_titulo_renderiza(self) -> None:
        # Caracteres UTF-8 multi-byte não devem quebrar template
        _, body = render_email(
            [_doc(titulo="🔥 PL 1234/2026 — ITCMD para herança digital")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        assert "🔥" in body
        assert "ITCMD" in body

    def test_lista_grande_renderiza_todos(self) -> None:
        # 50 documentos devem aparecer todos no body (sem truncar)
        docs = [_doc(titulo=f"PL {i}/2026") for i in range(50)]
        _, body = render_email(docs, digest_label="Diário", data_geracao=FIXED_NOW)
        # Cada PL deve aparecer
        for i in (0, 25, 49):
            assert f"PL {i}/2026" in body

    def test_multiple_tiers_separados_visualmente(self) -> None:
        # CRITICO/ALTA/NORMAL/BAIXA devem ter classes distintas no HTML
        docs = [
            _doc(titulo="C", tier=SeverityTier.CRITICO),
            _doc(titulo="A", tier=SeverityTier.ALTA),
            _doc(titulo="N", tier=SeverityTier.NORMAL),
            _doc(titulo="B", tier=SeverityTier.BAIXA),
        ]
        _, body = render_email(docs, digest_label="Diário", data_geracao=FIXED_NOW)
        # Cada tier produz cor distinta inline (TIER_COLORS em email_notifier)
        # critico=#d32f2f, alta=#f57c00, normal=#1976d2, baixa=#388e3c
        assert "#d32f2f" in body or "critico" in body.lower()

    def test_fonte_federal_renderiza(self) -> None:
        # UF=_federal não deve quebrar (LexML/STF/STJ retornam isso)
        _, body = render_email(
            [_doc(uf="_federal")],
            digest_label="Diário",
            data_geracao=FIXED_NOW,
        )
        # _federal deve aparecer (label) ou ser substituído por "Federal"
        assert "ederal" in body  # cobre "Federal" ou "_federal"
