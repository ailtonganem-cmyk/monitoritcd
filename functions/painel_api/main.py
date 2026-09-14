"""Cloud Function HTTPS — API do painel (Hosting faz rewrite de /api/**)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import functions_framework
from flask import Request, Response

from monitoritcd.core.source_loader import SourceConfigError
from monitoritcd.painel import EMAIL_PERMITIDO
from monitoritcd.painel.auth import (
    AuthPainelError,
    emitir_sessao,
    ler_sessao,
    parse_json_body,
    verificar_id_token,
)
from monitoritcd.painel.fontes import (
    excluir_fonte,
    incluir_fonte,
    listar_fontes,
    selecionar_fonte,
    ufs_validas,
)
from monitoritcd.painel.http import COOKIE, _client_id, _cookie_attrs, _hml_local, _secret
from monitoritcd.painel.ia_provedores import catalogo as catalogo_ia
from monitoritcd.painel.ia_provedores import gravar as gravar_ia
from monitoritcd.painel.ia_provedores import listar as listar_ia
from monitoritcd.painel.parametros import gravar_extras, listar_parametros

logger = logging.getLogger("painel_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _raiz() -> Path:
    env = os.environ.get("MONITORITCD_ROOT", "").strip()
    return Path(env) if env else Path(__file__).resolve().parent


def _json(codigo: int, payload: dict, *, set_cookie: str | None = None) -> Response:
    corpo = json.dumps(payload, ensure_ascii=False)
    resp = Response(corpo, status=codigo, mimetype="application/json")
    resp.headers["Cache-Control"] = "no-store"
    if set_cookie is not None:
        resp.headers["Set-Cookie"] = set_cookie
    return resp


def _cookie(request: Request) -> str:
    return (request.cookies.get(COOKIE) or "").strip()


def _email(request: Request) -> str | None:
    return ler_sessao(_cookie(request), _secret())


@functions_framework.http
def painel_api(request: Request) -> Response:  # noqa: PLR0912
    os.environ.setdefault("MONITORITCD_ROOT", str(_raiz()))
    path = request.path
    host = request.headers.get("Host") or ""
    method = request.method.upper()

    if method == "GET" and path == "/api/me":
        email = _email(request)
        hml = _hml_local(host)
        if not email:
            return _json(
                200,
                {
                    "ok": False,
                    "erro": "não autenticado",
                    "client_id": _client_id(),
                    "hml_local": hml,
                },
            )
        return _json(
            200,
            {"ok": True, "email": email, "client_id": _client_id(), "hml_local": hml},
        )
    if method == "GET" and path == "/api/fontes":
        if not _email(request):
            return _json(401, {"ok": False, "erro": "não autenticado"})
        return _json(200, {"ok": True, "itens": listar_fontes(_raiz()), "ufs": list(ufs_validas())})
    if method == "GET" and path == "/api/parametros":
        if not _email(request):
            return _json(401, {"ok": False, "erro": "não autenticado"})
        return _json(200, {"ok": True, **listar_parametros(_raiz())})
    if method == "GET" and path == "/api/ia":
        if not _email(request):
            return _json(401, {"ok": False, "erro": "não autenticado"})
        return _json(200, {"ok": True, "itens": listar_ia(_raiz()), "catalogo": catalogo_ia()})

    if method != "POST":
        return _json(405, {"ok": False, "erro": "método não permitido"})

    try:
        data = parse_json_body(request.get_data() or b"")
    except (ValueError, json.JSONDecodeError):
        return _json(400, {"ok": False, "erro": "JSON inválido"})

    if path == "/api/auth/google":
        try:
            email = verificar_id_token(str(data.get("id_token") or ""), client_id=_client_id())
        except AuthPainelError as exc:
            return _json(403, {"ok": False, "erro": str(exc)})
        sessao = emitir_sessao(email, _secret())
        return _json(
            200,
            {"ok": True, "email": email},
            set_cookie=f"{COOKIE}={sessao}; {_cookie_attrs()}; Max-Age=43200",
        )
    if path == "/api/auth/hml":
        if not _hml_local(host):
            return _json(403, {"ok": False, "erro": "login HML só em 127.0.0.1 e ENV≠production"})
        sessao = emitir_sessao(EMAIL_PERMITIDO, _secret())
        return _json(
            200,
            {"ok": True, "email": EMAIL_PERMITIDO, "hml_local": True},
            set_cookie=f"{COOKIE}={sessao}; {_cookie_attrs()}; Max-Age=43200",
        )
    if path == "/api/auth/sair":
        return _json(
            200,
            {"ok": True},
            set_cookie=f"{COOKIE}=; {_cookie_attrs()}; Max-Age=0",
        )

    if not _email(request):
        return _json(401, {"ok": False, "erro": "não autenticado"})

    try:
        if path == "/api/fontes/selecionar":
            item = selecionar_fonte(
                str(data.get("id") or ""), bool(data.get("selecionada")), raiz=_raiz()
            )
            return _json(200, {"ok": True, "item": item})
        if path == "/api/fontes/incluir":
            item = incluir_fonte(
                fonte_id=str(data.get("id") or ""),
                uf=str(data.get("uf") or ""),
                nome=str(data.get("nome") or ""),
                url=str(data.get("url") or ""),
                parser=str(data.get("parser") or "generic_html"),
                tipo=str(data.get("tipo") or "noticia"),
                raiz=_raiz(),
            )
            return _json(200, {"ok": True, "item": item})
        if path == "/api/fontes/excluir":
            excluir_fonte(str(data.get("id") or ""), raiz=_raiz())
            return _json(200, {"ok": True})
        if path == "/api/parametros":
            extras = data.get("extras")
            if not isinstance(extras, list):
                raise SourceConfigError("extras deve ser lista")
            return _json(200, {"ok": True, **gravar_extras(_raiz(), extras)})
        if path == "/api/ia":
            itens = data.get("itens")
            if not isinstance(itens, list):
                raise SourceConfigError("itens deve ser lista")
            return _json(200, {"ok": True, "itens": gravar_ia(_raiz(), itens)})
        if path == "/api/coleta":
            return _disparar_coleta(data)
    except SourceConfigError as exc:
        return _json(400, {"ok": False, "erro": str(exc)})
    return _json(404, {"ok": False, "erro": "não encontrado"})


def _disparar_coleta(data: dict) -> Response:
    """Dispara a Function monitor_cron; não espera o fim da pipeline."""
    import urllib.request  # noqa: PLC0415

    url = os.environ.get("MONITOR_CRON_URL", "").strip()
    token = os.environ.get("MONITOR_CRON_TOKEN", "").strip()
    if not url:
        return _json(
            200,
            {
                "ok": True,
                "aceito": False,
                "erro": "MONITOR_CRON_URL ausente",
                "comando": "python -m monitoritcd.main run",
            },
        )
    req = urllib.request.Request(url, data=b"{}", method="POST")  # noqa: S310
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Cron-Token", token)
    try:
        urllib.request.urlopen(req, timeout=10)  # noqa: S310
    except Exception as exc:
        logger.warning("painel.coleta_disparo_falhou %s", type(exc).__name__)
        return _json(502, {"ok": False, "erro": "falha ao disparar coleta"})
    return _json(
        200,
        {
            "ok": True,
            "aceito": True,
            "dry_run": bool(data.get("dry_run", False)),
            "source_id": data.get("source_id") or None,
        },
    )
