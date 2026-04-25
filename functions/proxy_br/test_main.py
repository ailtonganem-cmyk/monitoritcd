"""Testes da Cloud Function proxy_br.

Cobre:
- Auth (token correto, errado, ausente)
- Whitelist anti-SSRF (gov.br/jus.br aceitos; outros rejeitados)
- Schemes (apenas https)
- Erros do upstream (timeout, 5xx)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from functions.proxy_br.main import _is_allowed_host, _validate_target, proxy_br


def _request(*, args: dict[str, str] | None = None, headers: dict[str, str] | None = None):
    req = MagicMock()
    req.args = args or {}
    req.headers = headers or {}
    req.remote_addr = "127.0.0.1"
    return req


@pytest.fixture(autouse=True)
def _set_token() -> None:
    os.environ["PROXY_TOKEN"] = "test-token-123"


class TestIsAllowedHost:
    def test_gov_br_subdomain(self) -> None:
        assert _is_allowed_host("dadosabertos.almg.gov.br")

    def test_jus_br(self) -> None:
        assert _is_allowed_host("www.tjmg.jus.br")

    def test_leg_br(self) -> None:
        assert _is_allowed_host("www.al.go.leg.br")

    def test_external_rejected(self) -> None:
        assert not _is_allowed_host("evil.example.com")

    def test_lookalike_rejected(self) -> None:
        # Anti-trickery: "gov.br.evil.com" não passa
        assert not _is_allowed_host("gov.br.evil.com")


class TestValidateTarget:
    def test_https_gov_br_allowed(self) -> None:
        ok, _ = _validate_target("https://dadosabertos.almg.gov.br/api/v2/x")
        assert ok

    def test_http_blocked(self) -> None:
        ok, reason = _validate_target("http://example.gov.br/")
        assert not ok
        assert "scheme" in reason

    def test_external_blocked(self) -> None:
        ok, reason = _validate_target("https://evil.com/")
        assert not ok
        assert "whitelist" in reason

    def test_no_hostname(self) -> None:
        ok, reason = _validate_target("https://")
        assert not ok
        assert "hostname" in reason


class TestProxyBR:
    def test_missing_token_returns_401(self) -> None:
        resp = proxy_br(_request())
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self) -> None:
        resp = proxy_br(_request(headers={"X-Proxy-Token": "wrong"}))
        assert resp.status_code == 401

    def test_missing_url_returns_400(self) -> None:
        resp = proxy_br(_request(headers={"X-Proxy-Token": "test-token-123"}))
        assert resp.status_code == 400

    def test_blocked_host_returns_403(self) -> None:
        resp = proxy_br(
            _request(
                args={"url": "https://evil.example.com/"},
                headers={"X-Proxy-Token": "test-token-123"},
            )
        )
        assert resp.status_code == 403

    def test_proxies_allowed_host(self) -> None:
        with patch("functions.proxy_br.main.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.content = b'{"ok": true}'
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            resp = proxy_br(
                _request(
                    args={"url": "https://dadosabertos.almg.gov.br/api/v2/x"},
                    headers={"X-Proxy-Token": "test-token-123"},
                )
            )
            assert resp.status_code == 200

    def test_upstream_timeout_returns_504(self) -> None:
        with patch("functions.proxy_br.main.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.get.side_effect = httpx.ConnectTimeout("timeout")
            mock_client_cls.return_value = mock_client

            resp = proxy_br(
                _request(
                    args={"url": "https://dadosabertos.almg.gov.br/api/v2/x"},
                    headers={"X-Proxy-Token": "test-token-123"},
                )
            )
            assert resp.status_code == 504

    def test_misconfigured_returns_500(self) -> None:
        del os.environ["PROXY_TOKEN"]
        resp = proxy_br(_request())
        assert resp.status_code == 500
