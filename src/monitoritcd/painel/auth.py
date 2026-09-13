"""Login Google do painel — allowlist rígida, sem Rules/IAM Firebase."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from monitoritcd.painel import EMAIL_PERMITIDO

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
SESSAO_TTL_S = 12 * 3600


class AuthPainelError(ValueError):
    """Token inválido ou e-mail fora da allowlist."""


def verificar_id_token(id_token: str, *, client_id: str) -> str:
    """Valida o JWT do Google Identity Services e devolve o e-mail.

    Raises:
        AuthPainelError: token vazio, Google recusou, e-mail não verificado
            ou diferente de `EMAIL_PERMITIDO`.
    """
    token = (id_token or "").strip()
    if not token or not client_id.strip():
        raise AuthPainelError("token ou client_id ausente")
    try:
        resp = httpx.get(TOKENINFO_URL, params={"id_token": token}, timeout=10.0)
    except httpx.HTTPError as exc:
        raise AuthPainelError("falha ao validar token no Google") from exc
    if resp.status_code != 200:  # noqa: PLR2004
        raise AuthPainelError("token Google recusado")
    dados: dict[str, Any] = resp.json()
    if dados.get("aud") != client_id:
        raise AuthPainelError("audience do token não confere")
    email = str(dados.get("email") or "").strip().lower()
    if dados.get("email_verified") not in ("true", True):
        raise AuthPainelError("e-mail Google não verificado")
    if email != EMAIL_PERMITIDO:
        raise AuthPainelError("conta não autorizada neste painel")
    return email


def emitir_sessao(email: str, secret: str, *, agora: int | None = None) -> str:
    """Cookie assinado `email|exp|mac`."""
    exp = (agora if agora is not None else int(time.time())) + SESSAO_TTL_S
    corpo = f"{email}|{exp}"
    mac = hmac.new(secret.encode("utf-8"), corpo.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{corpo}|{mac}"


def ler_sessao(valor: str, secret: str, *, agora: int | None = None) -> str | None:
    """Devolve o e-mail se a sessão for válida; senão None."""
    partes = (valor or "").split("|")
    if len(partes) != 3:  # noqa: PLR2004
        return None
    email, exp_s, mac = partes
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if email.lower() != EMAIL_PERMITIDO:
        return None
    agora_i = agora if agora is not None else int(time.time())
    if exp < agora_i:
        return None
    corpo = f"{email}|{exp_s}"
    esperado = hmac.new(secret.encode("utf-8"), corpo.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, esperado):
        return None
    return email.lower()


def parse_json_body(raw: bytes) -> dict[str, Any]:
    """JSON de POST; vazio vira dict vazio."""
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON deve ser objeto")
    return data
