"""Testes unit do collector IOF/MG.

Cobre as partes puras (sem rede):
- `_unwrap_pkcs7_to_pdf`: extração do PDF de envelope PKCS#7 (happy path + erros)
- `_ACT_HEADER_RE`: regex de cabeçalhos de atos
- `_parse_acts`: fatiamento de texto em atos
- `_filter_by_source_terms`: filtro local por org_mentions/keywords
- `_normalize_for_match`: paridade com filters/keywords._normalize

Integration tests (full flow com httpx mock) ficam em tests/integration/.
"""

from __future__ import annotations

import io

import pypdf
import pytest

from monitoritcd.collectors.custom.iof_mg import (
    _ACT_HEADER_RE,
    IOFMGCollector,
    _normalize_for_match,
    _unwrap_pkcs7_to_pdf,
)
from monitoritcd.core import limits
from monitoritcd.core.base_collector import CollectorError
from monitoritcd.core.models import Parser, Source, TipoFonte


def _make_iof_source(
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


def _make_minimal_pdf(content_text: str = "Hello") -> bytes:
    """Gera um PDF mínimo válido via pypdf, com 1 página."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=72 * 8.5, height=72 * 11)
    buf = io.BytesIO()
    writer.write(buf)
    pdf = buf.getvalue()
    assert pdf.startswith(b"%PDF-")
    return pdf


# ─────────────────────────────────────────────────────────────────────────────
# _unwrap_pkcs7_to_pdf
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestUnwrapPkcs7:
    def test_extracts_pdf_from_envelope_with_prefix_bytes(self) -> None:
        """PKCS#7 envelope = bytes arbitrários + %PDF- + ... + %%EOF + (talvez assinatura)."""
        pdf = _make_minimal_pdf()
        envelope = b"\x30\x80" + b"\x00" * 50 + pdf + b"\x00\x01\x02"  # prefixo + PDF + sufixo
        extracted = _unwrap_pkcs7_to_pdf(envelope, source_id="doe-mg")
        assert extracted.startswith(b"%PDF-")
        assert extracted.endswith(b"%%EOF")

    def test_returns_pdf_unchanged_when_no_extra_bytes(self) -> None:
        """Sem trailing bytes além do PDF, o extraído termina em %%EOF (sem \\n trailing)."""
        pdf = _make_minimal_pdf()
        extracted = _unwrap_pkcs7_to_pdf(pdf, source_id="doe-mg")
        assert extracted.endswith(b"%%EOF")
        # extracted é prefixo do pdf (corte pode incluir ou não \n após EOF).
        assert pdf.startswith(extracted)

    def test_raises_when_no_pdf_magic(self) -> None:
        envelope = b"\x30\x80" + b"\x00" * 100  # PKCS#7-looking bytes mas sem PDF dentro
        with pytest.raises(CollectorError) as exc:
            _unwrap_pkcs7_to_pdf(envelope, source_id="doe-mg")
        assert "não contém %PDF-" in str(exc.value)

    def test_raises_when_pdf_exceeds_max_bytes(self) -> None:
        # PDF "válido" com tamanho enorme — usamos %PDF- + EOF distantes.
        huge_pdf = b"%PDF-1.4\n" + b"X" * (limits.MAX_PDF_BYTES + 100) + b"\n%%EOF"
        envelope = b"\x30\x80" + huge_pdf
        with pytest.raises(CollectorError) as exc:
            _unwrap_pkcs7_to_pdf(envelope, source_id="doe-mg")
        assert "excede MAX_PDF_BYTES" in str(exc.value)

    def test_truncates_at_last_eof(self) -> None:
        """Se há trailing bytes após %%EOF (típico de PKCS#7), termina no EOF."""
        pdf = _make_minimal_pdf()
        envelope = pdf + b"trailing-signature-bytes-after-eof"
        extracted = _unwrap_pkcs7_to_pdf(envelope, source_id="doe-mg")
        assert extracted.endswith(b"%%EOF")
        assert b"trailing-signature" not in extracted


# ─────────────────────────────────────────────────────────────────────────────
# _ACT_HEADER_RE
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestActHeaderRegex:
    @pytest.mark.parametrize(
        ("text", "expected_tipo"),
        [
            ("DECRETO Nº 529, DE 18 DE MAIO DE 2026", "DECRETO"),
            ("PORTARIA Nº 123", "PORTARIA"),
            ("PORTARIA SUFI Nº 99", "PORTARIA SUFI"),
            ("RESOLUÇÃO Nº 5.832", "RESOLUÇÃO"),
            ("RESOLUÇÃO SUFI Nº 5.832", "RESOLUÇÃO SUFI"),
            ("INSTRUÇÃO NORMATIVA Nº 003", "INSTRUÇÃO NORMATIVA"),
            ("EXTRATO Nº 7", "EXTRATO"),
            ("EDITAL Nº 1/2026", "EDITAL"),
            ("DECRETO NE Nº 529", "DECRETO NE"),
        ],
    )
    def test_matches_common_act_headers(self, text: str, expected_tipo: str) -> None:
        m = _ACT_HEADER_RE.search(text)
        assert m is not None, f"falhou em casar {text!r}"
        assert (m.group("tipo") or "").upper().startswith(expected_tipo)

    def test_extracts_numero(self) -> None:
        m = _ACT_HEADER_RE.search("DECRETO Nº 529, DE 18 DE MAIO DE 2026")
        assert m is not None
        assert m.group("num") == "529"

    def test_handles_dotted_numero(self) -> None:
        m = _ACT_HEADER_RE.search("RESOLUÇÃO Nº 5.832, DE 1º DE JANEIRO")
        assert m is not None
        assert m.group("num") == "5.832"

    def test_does_not_match_inline_text(self) -> None:
        """Cabeçalho precisa estar em início de linha (MULTILINE), não no meio."""
        m = _ACT_HEADER_RE.search("conforme PORTARIA Nº 5 da SEFAZ-MG")
        # MULTILINE flag faz ^ casar com início de linha; aqui não há quebra.
        # O regex aceita whitespace inicial mas a linha não começa com PORTARIA.
        # Como o texto inteiro é 1 linha sem `\n`, ^ casa só no início absoluto.
        assert m is None


# ─────────────────────────────────────────────────────────────────────────────
# _parse_acts (via instância de IOFMGCollector)
# ─────────────────────────────────────────────────────────────────────────────


_SAMPLE_PDF_TEXT = """\
SECRETARIA DE ESTADO DE FAZENDA

PORTARIA SUFI Nº 99, DE 18 DE MAIO DE 2026
Designa servidor para função de fiscal da SEFAZ.
Considerando o disposto na Lei 14.941...
Art. 1º — Fica designado o servidor X para a função.

PORTARIA Nº 100, DE 18 DE MAIO DE 2026
Nomeação de cargo comissionado na Secretaria de Estado de Fazenda.
Art. 1º — Nomeia Y para o cargo de chefe.

POLÍCIA CIVIL DO ESTADO DE MINAS GERAIS

PORTARIA Nº 555, DE 18 DE MAIO DE 2026
Designa delegado titular. Sem relação com tributo.
"""


@pytest.mark.unit
class TestParseActs:
    def test_finds_three_acts(self) -> None:
        c = IOFMGCollector(_make_iof_source())
        acts = c._parse_acts(_SAMPLE_PDF_TEXT)
        assert len(acts) == 3

    def test_act_text_includes_body_up_to_next_header(self) -> None:
        c = IOFMGCollector(_make_iof_source())
        acts = c._parse_acts(_SAMPLE_PDF_TEXT)
        # Primeiro ato: PORTARIA SUFI 99
        assert "fiscal da SEFAZ" in acts[0].texto
        assert "PORTARIA Nº 100" not in acts[0].texto  # corta antes do próximo
        # Segundo: PORTARIA 100
        assert "Secretaria de Estado de Fazenda" in acts[1].texto
        # Terceiro: PORTARIA 555 (sem SEFAZ)
        assert "delegado" in acts[2].texto

    def test_acts_have_tipo_and_numero(self) -> None:
        c = IOFMGCollector(_make_iof_source())
        acts = c._parse_acts(_SAMPLE_PDF_TEXT)
        assert acts[0].tipo == "PORTARIA SUFI"
        assert acts[0].numero == "99"
        assert acts[1].tipo == "PORTARIA"
        assert acts[1].numero == "100"
        assert acts[2].numero == "555"

    def test_empty_text_returns_empty_list(self) -> None:
        c = IOFMGCollector(_make_iof_source())
        assert c._parse_acts("") == []

    def test_no_headers_returns_empty(self) -> None:
        c = IOFMGCollector(_make_iof_source())
        assert c._parse_acts("apenas texto livre sem cabeçalhos") == []


# ─────────────────────────────────────────────────────────────────────────────
# _filter_by_source_terms
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFilterBySourceTerms:
    def test_keeps_only_acts_mentioning_org(self) -> None:
        # Inclui "Secretaria de Estado de Fazenda" porque Portaria 100 usa o
        # nome completo (não a sigla).
        src = _make_iof_source(org_mentions=["SEFAZ", "Secretaria de Estado de Fazenda"])
        c = IOFMGCollector(src)
        acts = c._parse_acts(_SAMPLE_PDF_TEXT)
        # 3 atos parseados; 2 mencionam SEFAZ (Portarias 99 e 100), 1 não (555).
        filtered = c._filter_by_source_terms(acts)
        assert len(filtered) == 2
        numeros = [a.numero for a in filtered]
        assert "99" in numeros
        assert "100" in numeros
        assert "555" not in numeros

    def test_no_filter_when_no_terms_configured(self) -> None:
        """Source sem org_mentions e sem keywords_required: collector deixa passar tudo
        (o orquestrador aplicará KEYWORDS_DEFAULT depois)."""
        # Source não pode ter keywords_bypass=True sem org_mentions (validador rejeita).
        src = Source(
            id="x",
            uf="MG",
            nome="x",
            tipo=TipoFonte.DOE,
            parser=Parser.IOF_MG,
            url="https://x.gov.br/",
            keywords_bypass=False,
            org_mentions=None,
        )
        c = IOFMGCollector(src)
        acts = c._parse_acts(_SAMPLE_PDF_TEXT)
        assert c._filter_by_source_terms(acts) == acts

    def test_keyword_required_also_works(self) -> None:
        """keywords_required preenchido (sem bypass) também filtra localmente."""
        src = Source(
            id="x",
            uf="MG",
            nome="x",
            tipo=TipoFonte.DOE,
            parser=Parser.IOF_MG,
            url="https://x.gov.br/",
            keywords_required=["fiscal"],
            keywords_bypass=False,
            org_mentions=None,
        )
        c = IOFMGCollector(src)
        acts = c._parse_acts(_SAMPLE_PDF_TEXT)
        filtered = c._filter_by_source_terms(acts)
        # Só o ato 99 fala em "fiscal".
        assert len(filtered) == 1
        assert filtered[0].numero == "99"


# ─────────────────────────────────────────────────────────────────────────────
# _normalize_for_match — paridade com filters/keywords._normalize
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestNormalizeForMatch:
    def test_lowercase_and_strip(self) -> None:
        assert _normalize_for_match("  Diário do Executivo  ") == "diário do executivo"

    def test_collapse_whitespace(self) -> None:
        assert _normalize_for_match("a\n\t  b") == "a b"

    def test_nfkc_normalization(self) -> None:
        # Compatibility chars: parêntese fullwidth (U+FF08) vira parêntese normal.
        text = "SEFAZ（MG）"  # noqa: RUF001 - intencional (testa NFKC)
        assert "(" in _normalize_for_match(text)


# ─────────────────────────────────────────────────────────────────────────────
# _MAX_ACTS_PER_RUN guard
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMaxActsGuard:
    def test_max_acts_constant_reasonable(self) -> None:
        """Sanity: MAX_ACTS_PER_RUN cobre dias atípicos (>500 atos é típico)."""
        from monitoritcd.collectors.custom.iof_mg import _MAX_ACTS_PER_RUN  # noqa: PLC0415

        assert 500 < _MAX_ACTS_PER_RUN < 10_000
