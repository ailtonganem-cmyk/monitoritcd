"""Detector puro de zeros consecutivos por fonte (issue #38)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from monitoritcd.core import limits
from monitoritcd.core.models import Parser, Source, TipoFonte
from monitoritcd.observability.source_run_health import (
    SourceRunHealth,
    apply_run_counts,
    effective_expected_min_items,
)

NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=UTC)
OWNER = "owner-test"


def _source(**kwargs: object) -> Source:
    payload: dict[str, object] = {
        "id": "src-x",
        "uf": "MG",
        "nome": "x",
        "tipo": TipoFonte.DOE,
        "parser": Parser.GENERIC_HTML,
        "url": "https://x.gov.br/",
    }
    payload.update(kwargs)
    return Source(**payload)  # type: ignore[arg-type]


def _apply(
    previous: SourceRunHealth | None,
    items_count: int,
    *,
    now: datetime = NOW,
) -> tuple[SourceRunHealth, bool]:
    return apply_run_counts(
        previous,
        source_id="src-x",
        owner_id=OWNER,
        items_count=items_count,
        now=now,
    )


@pytest.mark.unit
class TestEffectiveExpectedMinItems:
    def test_fragile_sem_campo_retorna_1(self) -> None:
        assert effective_expected_min_items(_source(fragile=True)) == 1

    def test_campo_explicito_zero_e_opt_out_mesmo_fragile(self) -> None:
        src = _source(fragile=True, expected_min_items_per_week=0)
        assert effective_expected_min_items(src) == 0

    def test_campo_explicito_positivo_opt_in_sem_fragile(self) -> None:
        src = _source(expected_min_items_per_week=3)
        assert effective_expected_min_items(src) == 3

    def test_sem_campo_nem_fragile_nao_monitora_alerta(self) -> None:
        assert effective_expected_min_items(_source()) is None


@pytest.mark.unit
class TestApplyRunCounts:
    def test_items_positivos_resetam_e_nao_alertam(self) -> None:
        prev, _ = _apply(None, 0)
        updated, alert = _apply(prev, 4)
        assert alert is False
        assert updated.consecutive_zero_runs == 0
        assert updated.last_nonzero_at == NOW
        assert updated.last_items_count == 4
        assert updated.last_run_at == NOW

    def test_zero_incrementa_sem_cruzar_limiar(self) -> None:
        health = None
        for _ in range(6):
            health, alert = _apply(health, 0)
            assert alert is False
        assert health is not None
        assert health.consecutive_zero_runs == 6
        assert health.last_nonzero_at is None

    def test_cruzamento_unico_no_setimo_zero(self) -> None:
        """Prova de mutação informal: se o incremento/cruzamento for removido, falha.

        Sete zeros seguidos disparam exatamente uma vez, quando consecutive == 7.
        """
        health = None
        alerts: list[bool] = []
        for _ in range(10):
            health, alert = _apply(health, 0)
            alerts.append(alert)
        assert alerts[:6] == [False] * 6
        assert alerts[6] is True
        assert alerts[7:] == [False, False, False]
        assert health is not None
        assert health.consecutive_zero_runs == 10

    def test_intercalado_nao_alerta(self) -> None:
        health, alert = _apply(None, 0)
        assert alert is False
        health, alert = _apply(health, 2)
        assert alert is False
        assert health.consecutive_zero_runs == 0
        for _ in range(6):
            health, alert = _apply(health, 0)
            assert alert is False
        assert health.consecutive_zero_runs == 6

    def test_preserva_last_nonzero_quando_volta_a_zero(self) -> None:
        first = datetime(2026, 1, 1, tzinfo=UTC)
        health, _ = _apply(None, 1, now=first)
        later = datetime(2026, 1, 8, tzinfo=UTC)
        health, alert = _apply(health, 0, now=later)
        assert alert is False
        assert health.last_nonzero_at == first
        assert health.last_run_at == later

    def test_estado_inicial_none_com_items(self) -> None:
        health, alert = _apply(None, 1)
        assert alert is False
        assert health.consecutive_zero_runs == 0
        assert health.source_id == "src-x"
        assert health.owner_id == OWNER


@pytest.mark.unit
class TestSourceRunHealthModel:
    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourceRunHealth(
                owner_id=OWNER,
                source_id="src-x",
                last_run_at=NOW,
                injected="x",  # type: ignore[call-arg]
            )

    def test_consecutive_negativo_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            SourceRunHealth(
                owner_id=OWNER,
                source_id="src-x",
                last_run_at=NOW,
                consecutive_zero_runs=-1,
            )

    def test_consecutive_acima_do_teto_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            SourceRunHealth(
                owner_id=OWNER,
                source_id="src-x",
                last_run_at=NOW,
                consecutive_zero_runs=limits.MAX_CONSECUTIVE_ZERO_RUNS + 1,
            )
