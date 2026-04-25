"""Testes anti-SSRF do `security.url_validator`.

Cobre todas as classes de URL que devem ser bloqueadas:
- Schemes não-HTTPS
- IPs em ranges privados (RFC1918, link-local, multicast, loopback)
- Cloud metadata endpoints (AWS, GCP, Azure)
- IPv6 link-local e ULA
- Hostnames suspeitos (localhost variants)
"""

from __future__ import annotations

import contextlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from monitoritcd.core import limits
from monitoritcd.security.url_validator import (
    UnsafeURLError,
    is_safe_url,
    validate_url,
)


@pytest.mark.security
class TestSchemeBlocking:
    def test_http_blocked(self) -> None:
        with pytest.raises(UnsafeURLError, match="Scheme"):
            validate_url("http://www.google.com/")

    def test_file_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("file:///etc/passwd")

    def test_ftp_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("ftp://ftp.example.com/")

    def test_gopher_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("gopher://example.com/")

    def test_javascript_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("javascript:alert(1)")

    def test_data_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("data:text/html,<script>alert(1)</script>")

    def test_https_allowed(self) -> None:
        assert validate_url("https://www.fazenda.sp.gov.br/")


@pytest.mark.security
class TestRFC1918Blocking:
    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.255.255",
        ],
    )
    def test_private_ips_blocked(self, ip: str) -> None:
        with pytest.raises(UnsafeURLError, match="range não permitido"):
            validate_url(f"https://{ip}/")


@pytest.mark.security
class TestLoopbackBlocking:
    @pytest.mark.parametrize(
        "url",
        [
            "https://127.0.0.1/",
            "https://127.255.255.254/",
            "https://[::1]/",  # IPv6 loopback
        ],
    )
    def test_loopback_blocked(self, url: str) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url(url)

    def test_localhost_string_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("https://localhost/")


@pytest.mark.security
class TestLinkLocalBlocking:
    def test_ipv4_link_local_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("https://169.254.1.1/")

    def test_aws_metadata_endpoint_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("https://169.254.169.254/latest/meta-data/")


@pytest.mark.security
class TestCloudMetadataBlocking:
    @pytest.mark.parametrize(
        "host",
        [
            "metadata.google.internal",
            "metadata.aws.internal",
            "metadata.azure.com",
        ],
    )
    def test_metadata_hostname_blocked(self, host: str) -> None:
        with pytest.raises(UnsafeURLError, match="bloqueado"):
            validate_url(f"https://{host}/")


@pytest.mark.security
class TestMulticastReservedBlocking:
    @pytest.mark.parametrize(
        "ip",
        [
            "224.0.0.1",  # multicast
            "240.0.0.1",  # reserved
            "0.0.0.0",  # unspecified - testando que é bloqueado, não bind  # noqa: S104
        ],
    )
    def test_special_ranges_blocked(self, ip: str) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url(f"https://{ip}/")


@pytest.mark.security
class TestEdgeCases:
    def test_empty_url_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("")

    def test_url_too_long_blocked(self) -> None:
        long_url = "https://x.gov.br/" + "a" * limits.MAX_URL_LENGTH
        with pytest.raises(UnsafeURLError, match="MAX_URL_LENGTH"):
            validate_url(long_url)

    def test_url_without_host_blocked(self) -> None:
        with pytest.raises(UnsafeURLError):
            validate_url("https:///path")

    def test_normal_gov_br_allowed(self) -> None:
        assert validate_url("https://www.lexml.gov.br/busca/search")
        assert validate_url("https://portal.fazenda.sp.gov.br/")
        assert validate_url("https://www.al.sp.gov.br/")


@pytest.mark.security
class TestIsSafeURL:
    def test_returns_true_for_safe(self) -> None:
        assert is_safe_url("https://www.gov.br/") is True

    def test_returns_false_for_unsafe(self) -> None:
        assert is_safe_url("http://localhost/") is False
        assert is_safe_url("file:///etc/passwd") is False


@pytest.mark.security
class TestPropertyBased:
    @given(st.text(max_size=100))
    def test_never_crashes_on_arbitrary_input(self, text: str) -> None:
        # Não pode lançar nada além de UnsafeURLError
        with contextlib.suppress(UnsafeURLError):
            validate_url(text)
        # Outras exceções seriam falha
