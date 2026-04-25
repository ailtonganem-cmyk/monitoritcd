"""Validador anti-SSRF de URLs.

Rejeita URLs que possam ser usadas em ataques Server-Side Request Forgery:
- Schemes diferentes de `https` (proibimos `http`, `file`, `gopher`, `ftp`, etc.)
- Hosts em ranges privados (RFC1918, link-local, multicast, loopback)
- Cloud metadata endpoints (AWS, GCP, Azure)
- IPv6 link-local e ULA

Uso típico:
    >>> validate_url("https://www.fazenda.sp.gov.br/")
    'https://www.fazenda.sp.gov.br/'
    >>> validate_url("http://localhost/")
    Traceback (most recent call last):
    ...
    UnsafeURLError: Scheme não permitido: http

Princípio canônico 1 (CLAUDE.md): URLs de YAMLs de fontes são entrada externa.
Validar SEMPRE na carga.
"""

from __future__ import annotations

import ipaddress
from typing import Final
from urllib.parse import urlparse

from monitoritcd.core import limits

ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"https"})

# Allowlist de hosts que podem ser acessados via HTTP (sem TLS).
# Cada host nesta lista é uma exceção auditada: API governamental brasileira
# pública (read-only, sem credenciais) que não expõe HTTPS válido.
# Risco aceito: MITM verá conteúdo público (zero PII) e nenhum secret nosso.
HTTP_ALLOWED_HOSTS: Final[frozenset[str]] = frozenset(
    {
        # ALEP — Assembleia Legislativa do Paraná
        # API REST pública /api/public; HTTPS retorna 500 (proxy SSL handshake)
        "webservices.assembleia.pr.leg.br",
    }
)

# Hostnames bloqueados (cloud metadata, gateways suspeitos)
BLOCKED_HOSTNAMES: Final[frozenset[str]] = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.aws.internal",
        "metadata.azure.com",
        "169.254.169.254",  # AWS/GCP metadata IP
        "fd00:ec2::254",  # AWS IPv6 metadata
    }
)


class UnsafeURLError(ValueError):
    """URL não passou na validação anti-SSRF."""


def validate_url(url: str) -> str:
    """Valida URL ou levanta `UnsafeURLError`.

    Args:
        url: URL a validar.

    Returns:
        A própria URL (inalterada) se válida.

    Raises:
        UnsafeURLError: se URL falha em qualquer check.
    """
    if not url or not isinstance(url, str):
        msg = "URL vazia ou tipo inválido"
        raise UnsafeURLError(msg)

    if len(url) > limits.MAX_URL_LENGTH:
        msg = f"URL excede MAX_URL_LENGTH ({limits.MAX_URL_LENGTH})"
        raise UnsafeURLError(msg)

    try:
        parsed = urlparse(url)
    except ValueError as e:
        msg = f"URL malformada: {e}"
        raise UnsafeURLError(msg) from e

    # Host obrigatório (precisamos antes de checar scheme p/ HTTP allowlist)
    host = parsed.hostname
    if not host:
        msg = "URL sem host"
        raise UnsafeURLError(msg)

    host_lower = host.lower()

    # Scheme whitelist com exceção para HTTP em hosts auditados
    if parsed.scheme == "http":
        if host_lower not in HTTP_ALLOWED_HOSTS:
            msg = (
                f"HTTP só permitido em hosts da allowlist auditada; "
                f"{host_lower!r} não está. Use HTTPS."
            )
            raise UnsafeURLError(msg)
    elif parsed.scheme not in ALLOWED_SCHEMES:
        msg = f"Scheme não permitido: {parsed.scheme!r} (permitidos: https)"
        raise UnsafeURLError(msg)

    # Hosts bloqueados explicitamente (cloud metadata, localhost variants)
    if host_lower in BLOCKED_HOSTNAMES:
        msg = f"Host bloqueado (anti-SSRF): {host}"
        raise UnsafeURLError(msg)

    # Se host é IP literal, valida ranges privados
    try:
        ip = ipaddress.ip_address(host_lower)
    except ValueError:
        # Não é IP — é hostname; resolução DNS acontece em runtime no httpx.
        # Não há como pré-validar 100%; mas hostname dá log de auditoria.
        return url

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        msg = f"IP em range não permitido (anti-SSRF): {ip}"
        raise UnsafeURLError(msg)

    return url


def is_safe_url(url: str) -> bool:
    """Helper booleano. Use `validate_url` quando quiser exception detalhada."""
    try:
        validate_url(url)
    except UnsafeURLError:
        return False
    return True
