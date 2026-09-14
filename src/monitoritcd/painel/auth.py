"""Login Google do painel — allowlist rígida, sem Rules/IAM Firebase."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import firebase_admin  # type: ignore[import-untyped]
import httpx
from firebase_admin import auth as fb_auth  # type: ignore[import-untyped]

from monitoritcd.painel import EMAIL_PERMITIDO

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
SESSAO_TTL_S = 12 * 3600


class AuthPainelError(ValueError):
    """Token inválido ou e-mail fora da allowlist."""


def _email_allowlist(dados: dict[str, Any]) -> str:
    email = str(dados.get("email") or "").strip().lower()
    if dados.get("email_verified") not in ("true", True):
        raise AuthPainelError("e-mail Google não verificado")
    if email != EMAIL_PERMITIDO:
        raise AuthPainelError("conta não autorizada neste painel")
    return email


def _verificar_google(token: str, client_id: str) -> str:
    try:
        resp = httpx.get(TOKENINFO_URL, params={"id_token": token}, timeout=10.0)
    except httpx.HTTPError as exc:
        raise AuthPainelError("falha ao validar token no Google") from exc
    if resp.status_code != 200:  # noqa: PLR2004
        raise AuthPainelError("token Google recusado")
    dados: dict[str, Any] = resp.json()
    if dados.get("aud") != client_id:
        raise AuthPainelError("audience do token não confere")
    return _email_allowlist(dados)


def _verificar_firebase(token: str) -> str:
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app()
    try:
        dados = fb_auth.verify_id_token(token)
    except (ValueError, fb_auth.InvalidIdTokenError) as exc:
        raise AuthPainelError("token Firebase recusado") from exc
    return _email_allowlist(dados)


def verificar_id_token(id_token: str, *, client_id: str) -> str:
    """Valida JWT Google (GIS/OAuth) ou Firebase Auth e devolve o e-mail.

    Raises:
        AuthPainelError: token vazio, recusado, e-mail não verificado
            ou diferente de `EMAIL_PERMITIDO`.
    """
    token = (id_token or "").strip()
    if not token:
        raise AuthPainelError("token ou client_id ausente")
    if client_id.strip():
        try:
            return _verificar_google(token, client_id)
        except AuthPainelError as exc:
            msg = str(exc)
            if "recusado" not in msg and "falha ao validar" not in msg:
                raise
    return _verificar_firebase(token)


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
