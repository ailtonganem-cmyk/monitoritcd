"""Servidor HTTP local do painel (127.0.0.1). Sem Functions, sem Rules."""

from __future__ import annotations

import json
import os
import posixpath
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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
from monitoritcd.painel.ia_provedores import catalogo as catalogo_ia
from monitoritcd.painel.ia_provedores import gravar as gravar_ia
from monitoritcd.painel.ia_provedores import listar as listar_ia
from monitoritcd.painel.parametros import gravar_extras, listar_parametros

# Hosting + Cloud Run só encaminha o cookie `__session`.
COOKIE = "__session"
_REL_ESTATICO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_TIPOS_ESTATICOS = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


def _dir_angular() -> Path:
    return _raiz() / "apps" / "painel" / "dist" / "painel" / "browser"


def _arquivo_angular(path: str) -> tuple[bytes, str] | None:
    """Serve só arquivos que já existem no dist; o path do cliente nunca entra em join."""
    if path.startswith("/api"):
        return None
    raiz = _dir_angular()
    if not raiz.is_dir():
        return None
    pedido = posixpath.normpath(path.split("?", 1)[0].lstrip("/"))
    if pedido in {".", "/", ""}:
        pedido = "index.html"
    if pedido.startswith("..") or pedido.startswith("/") or not _REL_ESTATICO.fullmatch(pedido):
        return None
    raiz_r = raiz.resolve()
    for dirpath, dirnames, filenames in os.walk(raiz_r):
        dirnames[:] = [d for d in dirnames if d not in {".", ".."}]
        for nome in filenames:
            candidato = Path(dirpath) / nome
            rel = candidato.relative_to(raiz_r).as_posix()
            if rel == pedido:
                tipo = _TIPOS_ESTATICOS.get(candidato.suffix, "application/octet-stream")
                return candidato.read_bytes(), tipo
    if "." not in Path(pedido).name:
        index = raiz_r / "index.html"
        if index.is_file():
            return index.read_bytes(), "text/html; charset=utf-8"
    return None


def _raiz() -> Path:
    env = os.environ.get("MONITORITCD_ROOT", "").strip()
    return Path(env) if env else Path(__file__).resolve().parents[3]


def _secret() -> str:
    env = os.environ.get("PAINEL_SESSION_SECRET", "").strip()
    if env:
        return env
    path = _raiz() / "config" / "painel" / ".secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    gerado = secrets.token_urlsafe(32)
    path.write_text(gerado + "\n", encoding="utf-8")
    return gerado


def _client_id() -> str:
    return os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()


def _cookie_attrs() -> str:
    """HttpOnly; Secure em produção (Hosting HTTPS)."""
    base = "HttpOnly; SameSite=Lax; Path=/"
    if os.environ.get("ENV", "development") == "production":
        return f"{base}; Secure"
    return base


def _hml_local(host_header: str) -> bool:
    if os.environ.get("ENV", "development") == "production":
        return False
    host = host_header.split(":", maxsplit=1)[0].lower()
    return host in {"127.0.0.1", "localhost", "[::1]"}


class PainelHandler(BaseHTTPRequestHandler):
    server_version = "MonitorITCDPainel/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _cookie(self) -> str:
        raw = self.headers.get("Cookie") or ""
        for parte in raw.split(";"):
            if parte.strip().startswith(COOKIE + "="):
                return parte.strip().split("=", 1)[1]
        return ""

    def _email(self) -> str | None:
        return ler_sessao(self._cookie(), _secret())

    def _json(self, codigo: int, payload: dict[str, Any]) -> None:
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _html(self, codigo: int, corpo: bytes) -> None:
        self._bytes(codigo, corpo, "text/html; charset=utf-8")

    def _bytes(self, codigo: int, corpo: bytes, content_type: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or "0")
        if n <= 0:
            return b""
        return self.rfile.read(min(n, 1_000_000))

    def do_GET(self) -> None:  # noqa: PLR0911
        path = urlparse(self.path).path
        estatico = _arquivo_angular(path)
        if estatico is not None:
            self._bytes(200, estatico[0], estatico[1])
            return
        if path in {"/", "/index.html"}:
            html = (Path(__file__).resolve().parent / "templates" / "index.html").read_text(
                encoding="utf-8"
            )
            html = html.replace("{{CLIENT_ID}}", _client_id())
            html = html.replace("{{EMAIL}}", EMAIL_PERMITIDO)
            self._html(200, html.encode("utf-8"))
            return
        if path == "/api/me":
            email = self._email()
            hml = _hml_local(self.headers.get("Host") or "")
            if not email:
                self._json(
                    200,
                    {
                        "ok": False,
                        "erro": "não autenticado",
                        "client_id": _client_id(),
                        "hml_local": hml,
                    },
                )
                return
            self._json(
                200,
                {
                    "ok": True,
                    "email": email,
                    "client_id": _client_id(),
                    "hml_local": hml,
                },
            )
            return
        if path == "/api/fontes":
            if not self._email():
                self._json(401, {"ok": False, "erro": "não autenticado"})
                return
            self._json(
                200, {"ok": True, "itens": listar_fontes(_raiz()), "ufs": list(ufs_validas())}
            )
            return
        if path == "/api/parametros":
            if not self._email():
                self._json(401, {"ok": False, "erro": "não autenticado"})
                return
            self._json(200, {"ok": True, **listar_parametros(_raiz())})
            return
        if path == "/api/ia":
            if not self._email():
                self._json(401, {"ok": False, "erro": "não autenticado"})
                return
            self._json(
                200,
                {"ok": True, "itens": listar_ia(_raiz()), "catalogo": catalogo_ia()},
            )
            return
        self._json(404, {"ok": False, "erro": "não encontrado"})

    def do_POST(self) -> None:  # noqa: PLR0911,PLR0912,PLR0915
        path = urlparse(self.path).path
        try:
            data = parse_json_body(self._body())
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"ok": False, "erro": "JSON inválido"})
            return
        if path == "/api/auth/google":
            try:
                email = verificar_id_token(str(data.get("id_token") or ""), client_id=_client_id())
            except AuthPainelError as exc:
                self._json(403, {"ok": False, "erro": str(exc)})
                return
            sessao = emitir_sessao(email, _secret())
            corpo = json.dumps({"ok": True, "email": email}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header(
                "Set-Cookie",
                f"{COOKIE}={sessao}; {_cookie_attrs()}; Max-Age=43200",
            )
            self.end_headers()
            self.wfile.write(corpo)
            return
        if path == "/api/auth/hml":
            if not _hml_local(self.headers.get("Host") or ""):
                self._json(403, {"ok": False, "erro": "login HML só em 127.0.0.1 e ENV≠production"})
                return
            sessao = emitir_sessao(EMAIL_PERMITIDO, _secret())
            corpo = json.dumps({"ok": True, "email": EMAIL_PERMITIDO, "hml_local": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header(
                "Set-Cookie",
                f"{COOKIE}={sessao}; {_cookie_attrs()}; Max-Age=43200",
            )
            self.end_headers()
            self.wfile.write(corpo)
            return
        if path == "/api/auth/sair":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", "11")
            self.send_header("Set-Cookie", f"{COOKIE}=; {_cookie_attrs()}; Max-Age=0")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        if not self._email():
            self._json(401, {"ok": False, "erro": "não autenticado"})
            return
        try:
            if path == "/api/fontes/selecionar":
                item = selecionar_fonte(
                    str(data.get("id") or ""),
                    bool(data.get("selecionada")),
                    raiz=_raiz(),
                )
                self._json(200, {"ok": True, "item": item})
                return
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
                self._json(200, {"ok": True, "item": item})
                return
            if path == "/api/fontes/excluir":
                excluir_fonte(str(data.get("id") or ""), raiz=_raiz())
                self._json(200, {"ok": True})
                return
            if path == "/api/parametros":
                extras = data.get("extras")
                if not isinstance(extras, list):
                    raise SourceConfigError("extras deve ser lista")
                self._json(200, {"ok": True, **gravar_extras(_raiz(), extras)})
                return
            if path == "/api/ia":
                itens = data.get("itens")
                if not isinstance(itens, list):
                    raise SourceConfigError("itens deve ser lista")
                self._json(200, {"ok": True, "itens": gravar_ia(_raiz(), itens)})
                return
            if path == "/api/coleta":
                qs = parse_qs(urlparse(self.path).query)
                source_id = str(data.get("source_id") or qs.get("source_id", [""])[0] or "")
                dry = bool(data.get("dry_run", True))
                self._json(
                    200,
                    {
                        "ok": True,
                        "aceito": True,
                        "dry_run": dry,
                        "source_id": source_id or None,
                        "comando": "python -m monitoritcd.main run"
                        + (" --dry-run" if dry else "")
                        + (f" --source-id {source_id}" if source_id else ""),
                    },
                )
                return
        except SourceConfigError as exc:
            self._json(400, {"ok": False, "erro": str(exc)})
            return
        self._json(404, {"ok": False, "erro": "não encontrado"})


def servir(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Sobe o painel em loop (Ctrl+C para parar)."""
    from dotenv import load_dotenv  # noqa: PLC0415

    load_dotenv(_raiz() / ".env")
    httpd = ThreadingHTTPServer((host, port), PainelHandler)
    print(f"Painel MonitorITCD em http://{host}:{port}  (só {EMAIL_PERMITIDO})")
    httpd.serve_forever()
