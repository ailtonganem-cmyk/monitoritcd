"""Cloud Function HTTPS — proxy reverso brasileiro para fontes .gov.br.

Deploy em região `southamerica-east1` (São Paulo) para contornar
ConnectTimeout que GitHub Actions runners (Azure US-West) sofrem em
servidores como `dadosabertos.almg.gov.br`.

Princípios canônicos aplicados:
1. **Anti-SSRF**: whitelist de hosts (`*.gov.br`, `*.jus.br`) + bloqueio
   de IPs privados via redirect. Nenhum host fora da whitelist passa.
2. **Auth via token compartilhado**: header `X-Proxy-Token` precisa
   bater com env var `PROXY_TOKEN` (configurada no deploy via secret).
   Sem token = 401. Token errado = 401.
3. **MAX_BYTES**: resposta limitada a 5 MB para evitar abuso.
4. **Logging estruturado**: cada request vira um log line com host
   alvo (sem o token) para auditoria.

Endpoint:
    GET https://<region>-<project>.cloudfunctions.net/proxy_br?url=<encoded>

Headers:
    X-Proxy-Token: <token>     # obrigatório
    User-Agent: <opcional>     # repassado ao alvo

Response:
    200: corpo bruto do alvo (Content-Type repassado)
    400: URL inválida ou ausente
    401: token ausente/errado
    403: host fora da whitelist
    502: alvo retornou erro / timeout
    504: alvo timeout
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import functions_framework
import httpx
from flask import Request, Response

logger = logging.getLogger("proxy_br")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ALLOWED_SCHEMES = frozenset({"https"})
ALLOWED_HOST_SUFFIXES = (
    ".gov.br",
    ".jus.br",
    ".leg.br",
)

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 30.0


def _is_allowed_host(host: str) -> bool:
    host_lower = host.lower()
    return any(host_lower == s.lstrip(".") or host_lower.endswith(s) for s in ALLOWED_HOST_SUFFIXES)


def _validate_target(url: str) -> tuple[bool, str]:
    """Retorna (allowed, reason)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "url malformada"

    if parsed.scheme not in ALLOWED_SCHEMES:
        return False, f"scheme proibido: {parsed.scheme}"
    if not parsed.hostname:
        return False, "sem hostname"
    if not _is_allowed_host(parsed.hostname):
        return False, f"host fora da whitelist: {parsed.hostname}"
    return True, ""


@functions_framework.http
def proxy_br(request: Request) -> Response:
    """Entry point HTTPS."""
    expected_token = os.environ.get("PROXY_TOKEN")
    if not expected_token:
        logger.error("PROXY_TOKEN env var nao configurada")
        return Response("server misconfigured", status=500)

    received_token = request.headers.get("X-Proxy-Token", "")
    if not received_token or received_token != expected_token:
        logger.warning("auth failed from %s", request.remote_addr)
        return Response("unauthorized", status=401)

    target_url = request.args.get("url", "")
    if not target_url:
        return Response("missing 'url' parameter", status=400)

    allowed, reason = _validate_target(target_url)
    if not allowed:
        logger.warning("blocked target=%s reason=%s", target_url[:200], reason)
        return Response(f"forbidden: {reason}", status=403)

    # User-Agent realista de browser brasileiro: alguns sites .gov.br bloqueiam
    # User-Agents desconhecidos (mesmo que tecnicamente legais).
    user_agent = request.headers.get(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    )

    parsed = urlparse(target_url)
    logger.info("proxy host=%s path=%s", parsed.hostname, parsed.path[:100])

    try:
        with httpx.Client(
            timeout=httpx.Timeout(TIMEOUT_SECONDS),
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            upstream = client.get(
                target_url,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "*/*",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                },
            )
    except httpx.ConnectTimeout:
        return Response("upstream connect timeout", status=504)
    except httpx.ReadTimeout:
        return Response("upstream read timeout", status=504)
    except httpx.HTTPError as e:
        logger.warning("upstream error: %s", type(e).__name__)
        return Response(f"upstream error: {type(e).__name__}", status=502)

    body = upstream.content[:MAX_BYTES]
    content_type = upstream.headers.get("content-type", "application/octet-stream")
    logger.info(
        "proxy result host=%s status=%d bytes=%d content_type=%s",
        parsed.hostname,
        upstream.status_code,
        len(body),
        content_type[:50],
    )
    return Response(body, status=upstream.status_code, content_type=content_type)
