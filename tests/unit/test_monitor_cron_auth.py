"""Auth fail-closed da Function monitor_cron."""

from __future__ import annotations

from monitoritcd.security.cron_auth import cron_autorizado


def test_sem_token_configurado_recusa() -> None:
    assert cron_autorizado({"Authorization": "Bearer x", "X-Cron-Token": "abc"}, env={}) is False


def test_sem_header_recusa() -> None:
    env = {"MONITOR_CRON_TOKEN": "segredo-cron"}
    assert cron_autorizado({"Authorization": "Bearer x"}, env=env) is False


def test_token_errado_recusa() -> None:
    env = {"MONITOR_CRON_TOKEN": "segredo-cron"}
    assert cron_autorizado({"X-Cron-Token": "outro"}, env=env) is False


def test_token_certo_aceita() -> None:
    env = {"MONITOR_CRON_TOKEN": "segredo-cron"}
    assert cron_autorizado({"X-Cron-Token": "segredo-cron"}, env=env) is True
