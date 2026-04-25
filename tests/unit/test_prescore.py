"""Testes do pré-score heurístico."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from monitoritcd.core.models import Parser, RawItem, Source, TipoFonte
from monitoritcd.filters.prescore import (
    DEFAULT_CUTOFF,
    passes_cutoff,
    prescore,
)

NOW = datetime.now(UTC)
HASH = "a" * 64


def _src(*, tipo: TipoFonte = TipoFonte.SEFAZ, trusted: bool = False) -> Source:
    return Source(
        id="x",
        uf="SP",
        nome="x",
        tipo=tipo,
        parser=Parser.GENERIC_HTML,
        url="https://x.gov.br/",
        trusted=trusted,
    )


def _raw(
    titulo: str = "Título sobre ITCMD em SP",
    texto: str | None = None,
    age_days: int = 0,
) -> RawItem:
    return RawItem(
        source_id="x",
        titulo_raw=titulo,
        url="https://x.gov.br/i",
        texto_raw=texto,
        data_publicacao=NOW - timedelta(days=age_days),
        fetched_at=NOW,
        content_hash=HASH,
    )


@pytest.mark.unit
class TestPrescore:
    def test_trusted_source_with_keywords_high_score(self) -> None:
        score = prescore(_raw(), _src(trusted=True), ["ITCMD"])
        assert score > 0.6

    def test_unrelated_source_no_keywords_low_score(self) -> None:
        score = prescore(
            _raw(titulo="Notícia sobre cinema", age_days=60),
            _src(tipo=TipoFonte.NOTICIA),
            [],
        )
        assert score < DEFAULT_CUTOFF

    def test_passes_cutoff_helper(self) -> None:
        assert passes_cutoff(0.5)
        assert passes_cutoff(0.3) is True
        assert passes_cutoff(0.29) is False

    def test_freshness_decreases_score(self) -> None:
        recent = prescore(_raw(age_days=0), _src(trusted=True), ["ITCMD"])
        old = prescore(_raw(age_days=60), _src(trusted=True), ["ITCMD"])
        assert recent > old

    def test_no_data_pub_uses_neutral(self) -> None:
        item = RawItem(
            source_id="x",
            titulo_raw="ITCMD",
            url="https://x.gov.br/i",
            data_publicacao=None,
            fetched_at=NOW,
            content_hash=HASH,
        )
        # Não crasha, retorna número válido
        score = prescore(item, _src(), ["ITCMD"])
        assert 0.0 <= score <= 1.0

    def test_authority_high_for_trusted(self) -> None:
        trusted_score = prescore(_raw(), _src(trusted=True), ["ITCMD"])
        nontrusted_score = prescore(_raw(), _src(trusted=False), ["ITCMD"])
        assert trusted_score > nontrusted_score

    def test_jurisprudencia_authority(self) -> None:
        score = prescore(_raw(), _src(tipo=TipoFonte.JURISPRUDENCIA), ["ITCMD"])
        assert 0.0 <= score <= 1.0

    def test_doutrina_lower_authority(self) -> None:
        sefaz_score = prescore(_raw(), _src(tipo=TipoFonte.SEFAZ), ["ITCMD"])
        doutrina_score = prescore(_raw(), _src(tipo=TipoFonte.DOUTRINA), ["ITCMD"])
        assert sefaz_score > doutrina_score

    def test_density_increases_with_keywords(self) -> None:
        few = prescore(_raw(texto="curto"), _src(), ["ITCMD"])
        many = prescore(_raw(texto="curto"), _src(), ["ITCMD", "ITCD", "doação"])
        assert many >= few

    def test_score_is_in_valid_range(self) -> None:
        for trusted in (True, False):
            for tipo in TipoFonte:
                for age in (0, 15, 60):
                    score = prescore(
                        _raw(age_days=age),
                        _src(tipo=tipo, trusted=trusted),
                        ["ITCMD"],
                    )
                    assert 0.0 <= score <= 1.0, f"Score fora de range: {score}"

    def test_naive_datetime_is_handled(self) -> None:
        # data_publicacao sem tzinfo — score não crasha
        item = RawItem(
            source_id="x",
            titulo_raw="ITCMD",
            url="https://x.gov.br/i",
            data_publicacao=datetime(2026, 1, 1),  # noqa: DTZ001 - testando naive
            fetched_at=NOW,
            content_hash=HASH,
        )
        score = prescore(item, _src(), ["ITCMD"])
        assert 0.0 <= score <= 1.0
