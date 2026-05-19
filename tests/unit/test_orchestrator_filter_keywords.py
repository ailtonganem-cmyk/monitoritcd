"""Testes do Filtro 1 (filter_by_keywords) com a combinação keywords_bypass x org_mentions.

Cobre os 3 combos válidos (o 4º — bypass=True sem org_mentions — é rejeitado no
construtor do Source, validado em test_models.py):

| bypass | org_mentions | item passa quando…                            |
|--------|--------------|-----------------------------------------------|
| False  | None         | keyword temática casa (comportamento legado)  |
| False  | ["SEFAZ"]    | keyword OU menção a SEFAZ casa (amplia)       |
| True   | ["SEFAZ"]    | menção a SEFAZ casa (keywords não exigidas)   |

Também garante que matched_keywords devolvidas para o prescore incluam menções
de órgão (alimentam o `_density_score`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from monitoritcd.core.models import Parser, RawItem, Source, TipoFonte
from monitoritcd.orchestrator import filter_by_keywords

NOW = datetime.now(UTC)
SAMPLE_HASH = "a" * 64


def _raw(titulo: str, texto: str | None = None) -> RawItem:
    return RawItem(
        source_id="src-test",
        titulo_raw=titulo,
        url="https://x.gov.br/a",
        fetched_at=NOW,
        content_hash=SAMPLE_HASH,
        texto_raw=texto,
    )


def _src(
    *,
    keywords_bypass: bool = False,
    org_mentions: list[str] | None = None,
    keywords_required: list[str] | None = None,
) -> Source:
    return Source(
        id="src-test",
        uf="MG",
        nome="Teste",
        tipo=TipoFonte.DOE,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
        keywords_required=keywords_required or [],
        keywords_bypass=keywords_bypass,
        org_mentions=org_mentions,
    )


@pytest.mark.unit
class TestFilterByKeywordsLegacyBehavior:
    """bypass=False, org_mentions=None — só keyword temática deve fazer passar."""

    def test_item_com_keyword_itcd_passa(self) -> None:
        src = _src()
        item = _raw("Decreto sobre ITCMD progressivo em SP")
        result = filter_by_keywords([(src, item)])
        assert len(result) == 1
        _, _, kws = result[0]
        assert any("ITCMD" in k for k in kws)

    def test_item_sem_keyword_rejeitado(self) -> None:
        src = _src()
        item = _raw("Designação de servidor")
        result = filter_by_keywords([(src, item)])
        assert result == []


@pytest.mark.unit
class TestFilterByKeywordsWithOrgMentions:
    """bypass=False, org_mentions=['SEFAZ'] — keyword OU menção a órgão amplia captura."""

    def test_keyword_passa(self) -> None:
        src = _src(org_mentions=["SEFAZ"])
        item = _raw("Decreto sobre ITCMD em MG")
        result = filter_by_keywords([(src, item)])
        assert len(result) == 1

    def test_org_mention_passa_sem_keyword(self) -> None:
        src = _src(org_mentions=["SEFAZ", "Secretaria de Estado de Fazenda"])
        item = _raw("Portaria nomeia chefe de gabinete na SEFAZ")
        result = filter_by_keywords([(src, item)])
        assert len(result) == 1
        _, _, kws = result[0]
        assert "SEFAZ" in kws

    def test_sem_keyword_e_sem_mention_rejeitado(self) -> None:
        src = _src(org_mentions=["SEFAZ"])
        item = _raw("Designação de servidor na Secretaria de Educação")
        result = filter_by_keywords([(src, item)])
        assert result == []

    def test_org_mention_normaliza_nfkc_e_lower(self) -> None:
        src = _src(org_mentions=["Secretaria de Estado de Fazenda"])
        item = _raw("Portaria emitida pela SECRETARIA DE ESTADO DE FAZENDA")
        result = filter_by_keywords([(src, item)])
        assert len(result) == 1


@pytest.mark.unit
class TestFilterByKeywordsWithBypass:
    """bypass=True, org_mentions=['SEFAZ'] — só menção a órgão, ignora keywords."""

    def test_org_mention_passa(self) -> None:
        src = _src(keywords_bypass=True, org_mentions=["SEFAZ"])
        item = _raw("Portaria SEF nº 123 designa fiscal na SEFAZ")
        result = filter_by_keywords([(src, item)])
        assert len(result) == 1
        _, _, kws = result[0]
        assert "SEFAZ" in kws

    def test_sem_mention_rejeitado_mesmo_com_keyword(self) -> None:
        """Sob bypass, keyword ITCD não basta: precisa de menção ao órgão."""
        src = _src(keywords_bypass=True, org_mentions=["SEFAZ"])
        item = _raw("Decreto sobre ITCMD na Justiça Estadual")
        result = filter_by_keywords([(src, item)])
        assert result == []

    def test_org_mention_no_texto_raw_passa(self) -> None:
        """Menção pode aparecer no texto, não só no título."""
        src = _src(keywords_bypass=True, org_mentions=["SEFAZ"])
        item = _raw(
            "Decreto nº 529",
            texto="Resolve transferir competência da SEFAZ para a SES.",
        )
        result = filter_by_keywords([(src, item)])
        assert len(result) == 1


@pytest.mark.unit
class TestFilterByKeywordsMatchedReturnedForPrescore:
    """Itens passados precisam carregar 'matched' (keywords + menções de órgão sem duplicar)."""

    def test_combina_keywords_e_mentions_sem_duplicar(self) -> None:
        src = _src(org_mentions=["SEFAZ"])
        item = _raw("SEFAZ regulamenta ITCMD progressivo")
        result = filter_by_keywords([(src, item)])
        assert len(result) == 1
        _, _, kws = result[0]
        # Tem ambos termos: keyword ITCMD + menção SEFAZ
        assert any("ITCMD" in k for k in kws)
        assert "SEFAZ" in kws
        # Sem duplicatas
        assert len(kws) == len(set(kws))

    def test_bypass_devolve_apenas_org_mentions_casadas(self) -> None:
        src = _src(keywords_bypass=True, org_mentions=["SEFAZ", "SEF/MG"])
        item = _raw("Portaria SEF/MG nº 99 — nomeação")
        result = filter_by_keywords([(src, item)])
        assert len(result) == 1
        _, _, kws = result[0]
        assert "SEF/MG" in kws
