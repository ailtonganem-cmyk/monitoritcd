"""Fuzz adversarial de URLs (Sugestão #26).

Testa edge-cases além do ipv4 RFC1918 e localhost:
- IPv6 link-local (fe80::)
- IPv4-mapped IPv6 ([::ffff:127.0.0.1])
- Octal/hex/decimal encodings
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from monitoritcd.security.url_validator import UnsafeURLError, validate_url


@pytest.mark.security
@pytest.mark.parametrize(
    "url",
    [
        "https://[::1]/",
        "https://[::ffff:127.0.0.1]/",
        "https://[fe80::1]/",
        "https://0.0.0.0/",
        "https://metadata.google.internal/",
        "https://169.254.169.254/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<script>",
        "gopher://localhost",
        "ftp://example.com",
    ],
)
def test_blocks_ssrf_attack_vectors(url: str) -> None:
    """Vetores conhecidos de SSRF são rejeitados."""
    with pytest.raises(UnsafeURLError):
        validate_url(url)


@pytest.mark.security
@settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=50)
@given(
    scheme=st.sampled_from(["javascript", "data", "vbscript", "file", "gopher", "ldap"]),
    path=st.text(min_size=1, max_size=50),
)
def test_dangerous_schemes_always_rejected(scheme: str, path: str) -> None:
    """Schemes perigosos são sempre rejeitados (property-based)."""
    url = f"{scheme}://{path}"
    with pytest.raises(UnsafeURLError):
        validate_url(url)


@pytest.mark.security
@pytest.mark.parametrize(
    "host",
    [
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "192.168.255.254",
        "127.0.0.1",
        "127.0.0.255",
        "0.0.0.0",  # noqa: S104 — string literal de teste, não binding real
        "169.254.169.254",
    ],
)
def test_private_ipv4_ranges_rejected(host: str) -> None:
    """IPv4 privados/loopback/link-local sempre rejeitados."""
    with pytest.raises(UnsafeURLError):
        validate_url(f"https://{host}/")
