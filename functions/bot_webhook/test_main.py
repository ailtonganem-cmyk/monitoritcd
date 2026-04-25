"""Testes da Cloud Function bot_webhook.

Testa apenas a camada de webhook (auth, parsing, response).
A lógica de handlers é testada em tests/integration/test_bot_*.py.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


def _request(*, method="POST", json_body=None, headers=None):
    req = MagicMock()
    req.method = method
    req.headers = headers or {}
    req.remote_addr = "127.0.0.1"
    req.get_json = MagicMock(return_value=json_body or {})
    return req


@pytest.fixture(autouse=True)
def _set_env() -> None:
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-secret"


class TestBotWebhook:
    def test_get_returns_405(self) -> None:
        from functions.bot_webhook.main import bot_webhook  # noqa: PLC0415

        resp = bot_webhook(_request(method="GET"))
        assert resp.status_code == 405

    def test_no_token_returns_401(self) -> None:
        from functions.bot_webhook.main import bot_webhook  # noqa: PLC0415

        resp = bot_webhook(_request())
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self) -> None:
        from functions.bot_webhook.main import bot_webhook  # noqa: PLC0415

        resp = bot_webhook(_request(headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}))
        assert resp.status_code == 401

    def test_empty_payload_returns_200(self) -> None:
        from functions.bot_webhook.main import bot_webhook  # noqa: PLC0415

        resp = bot_webhook(_request(headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"}))
        assert resp.status_code == 200

    def test_valid_update_invokes_handle_update(self) -> None:
        with patch("functions.bot_webhook.main.asyncio.run") as mock_run:
            from functions.bot_webhook.main import bot_webhook  # noqa: PLC0415

            update = {
                "update_id": 12345,
                "message": {
                    "chat": {"id": 999},
                    "text": "/status",
                },
            }
            resp = bot_webhook(
                _request(
                    headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
                    json_body=update,
                )
            )
            assert resp.status_code == 200
            mock_run.assert_called_once()

    def test_handler_exception_still_returns_200(self) -> None:
        # Telegram não retentar se 200; falhas no processamento são logadas
        with patch("functions.bot_webhook.main.asyncio.run") as mock_run:
            mock_run.side_effect = RuntimeError("boom")

            from functions.bot_webhook.main import bot_webhook  # noqa: PLC0415

            resp = bot_webhook(
                _request(
                    headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
                    json_body={"update_id": 1, "message": {"chat": {"id": 1}}},
                )
            )
            assert resp.status_code == 200

    def test_no_secret_env_returns_401(self) -> None:
        del os.environ["TELEGRAM_WEBHOOK_SECRET"]
        from functions.bot_webhook.main import bot_webhook  # noqa: PLC0415

        resp = bot_webhook(_request(headers={"X-Telegram-Bot-Api-Secret-Token": "anything"}))
        assert resp.status_code == 401
