"""Testes da Cloud Function canary_filter."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from functions.canary_filter.main import (
    _extract_trigger_info,
    _is_scanner_ip,
    _is_scanner_ua,
    canary_filter,
)


def _request(*, method="POST", json_body=None, headers=None, args=None):
    req = MagicMock()
    req.method = method
    req.headers = headers or {}
    req.args = args or {}
    req.remote_addr = "127.0.0.1"
    req.get_json = MagicMock(return_value=json_body or {})
    return req


@pytest.fixture(autouse=True)
def _set_env() -> None:
    os.environ["FILTER_TOKEN"] = "test-filter"
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake:bot"
    os.environ["TELEGRAM_OWNER_CHAT_ID"] = "12345"


class TestIsScannerUA:
    def test_python_requests(self) -> None:
        assert _is_scanner_ua("python-requests/2.33.1")

    def test_go_http_client(self) -> None:
        assert _is_scanner_ua("Go-http-client/1.1")

    def test_curl(self) -> None:
        assert _is_scanner_ua("curl/7.84.0")

    def test_browser_passes(self) -> None:
        assert not _is_scanner_ua(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/132.0"
        )

    def test_empty(self) -> None:
        assert not _is_scanner_ua("")

    def test_aws_sdk(self) -> None:
        assert _is_scanner_ua("aws-sdk-go/1.0")


class TestIsScannerIP:
    def test_azure_us_west(self) -> None:
        # 52.161.50.35 estava no email real do canarytoken (Azure US-West)
        assert _is_scanner_ip("52.161.50.35")

    def test_aws_us(self) -> None:
        assert _is_scanner_ip("52.10.20.30")

    def test_brazil_residential(self) -> None:
        assert not _is_scanner_ip("177.10.20.30")  # Vivo BR range

    def test_invalid(self) -> None:
        assert not _is_scanner_ip("not-an-ip")


class TestExtractTriggerInfo:
    def test_canarytokens_format(self) -> None:
        payload = {
            "memo": "MonitorITCD repo",
            "channel": "AWS API Key",
            "time": "2026-04-25 19:54 UTC",
            "token": "wbvsademg2des6xd1my49aixf",
            "additional_info": {
                "useragent": "python-requests/2.33.1",
                "src_ip": "52.161.50.35",
            },
        }
        info = _extract_trigger_info(payload)
        assert info["user_agent"] == "python-requests/2.33.1"
        assert info["source_ip"] == "52.161.50.35"
        assert info["memo"] == "MonitorITCD repo"

    def test_missing_additional_info(self) -> None:
        info = _extract_trigger_info({"memo": "x"})
        assert info["user_agent"] == ""
        assert info["source_ip"] == ""


class TestCanaryFilter:
    def test_unauth_returns_401(self) -> None:
        req = _request(headers={"X-Canary-Filter-Token": "wrong"})
        resp = canary_filter(req)
        assert resp.status_code == 401

    def test_get_returns_405(self) -> None:
        req = _request(method="GET", args={"token": "test-filter"})
        resp = canary_filter(req)
        assert resp.status_code == 405

    def test_scanner_ua_filtered(self) -> None:
        req = _request(
            args={"token": "test-filter"},
            json_body={
                "memo": "test",
                "additional_info": {
                    "useragent": "python-requests/2.33.1",
                    "src_ip": "52.161.50.35",
                },
            },
        )
        resp = canary_filter(req)
        assert resp.status_code == 200
        assert b"filtered" in resp.data

    def test_human_ua_forwarded(self) -> None:
        # User-agent de browser real + IP residencial → considerado humano
        with patch("functions.canary_filter.main.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            req = _request(
                args={"token": "test-filter"},
                json_body={
                    "memo": "test",
                    "additional_info": {
                        "useragent": "Mozilla/5.0 Chrome/132.0",
                        "src_ip": "200.100.50.10",
                    },
                },
            )
            resp = canary_filter(req)
            assert resp.status_code == 200
            assert b"forwarded" in resp.data
            mock_client.post.assert_called_once()

    def test_no_filter_token_skips_auth(self) -> None:
        # Quando FILTER_TOKEN não setado, qualquer request passa auth
        del os.environ["FILTER_TOKEN"]
        req = _request(json_body={"memo": "x"})
        resp = canary_filter(req)
        # Sem UA suspeito + sem IP suspeito = forward (mas Telegram falha sem creds reais)
        assert resp.status_code == 200

    def test_telegram_failure_still_returns_200(self) -> None:
        # Canarytokens.org não retentar se 200; falha Telegram absorvida
        with patch("functions.canary_filter.main.httpx.Client") as mock_client_cls:
            import httpx

            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.post.side_effect = httpx.HTTPError("boom")
            mock_client_cls.return_value = mock_client

            req = _request(
                args={"token": "test-filter"},
                json_body={
                    "memo": "test",
                    "additional_info": {
                        "useragent": "Mozilla/5.0",
                        "src_ip": "200.100.50.10",
                    },
                },
            )
            resp = canary_filter(req)
            assert resp.status_code == 200
            assert b"telegram=False" in resp.data
