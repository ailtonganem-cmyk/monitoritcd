"""Painel local: auth allowlist, fontes operador, parâmetros e IA."""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path  # noqa: TC003

import httpx
import pytest
import yaml

from monitoritcd.core.source_loader import SourceConfigError
from monitoritcd.painel import EMAIL_PERMITIDO
from monitoritcd.painel.auth import (
    AuthPainelError,
    emitir_sessao,
    ler_sessao,
    parse_json_body,
    verificar_id_token,
)
from monitoritcd.painel.fontes import excluir_fonte, incluir_fonte, listar_fontes, selecionar_fonte
from monitoritcd.painel.http import PainelHandler
from monitoritcd.painel.ia_provedores import catalogo as catalogo_ia
from monitoritcd.painel.ia_provedores import gravar as gravar_ia
from monitoritcd.painel.ia_provedores import listar as listar_ia
from monitoritcd.painel.parametros import gravar_extras, listar_parametros


def test_sessao_roundtrip() -> None:
    token = emitir_sessao(EMAIL_PERMITIDO, "segredo", agora=1_000)
    assert ler_sessao(token, "segredo", agora=1_001) == EMAIL_PERMITIDO
    assert ler_sessao(token, "outro", agora=1_001) is None
    assert ler_sessao(token, "segredo", agora=1_000 + 13 * 3600) is None


def test_sessao_rejeita_outro_email() -> None:
    token = emitir_sessao("outra@gmail.com", "segredo", agora=1_000)
    assert ler_sessao(token, "segredo", agora=1_001) is None


def test_token_google_rejeita_email_estranho(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {
                "aud": "cid",
                "email": "intruso@gmail.com",
                "email_verified": "true",
            }

    monkeypatch.setattr("monitoritcd.painel.auth.httpx.get", lambda *a, **k: _Resp())
    with pytest.raises(AuthPainelError, match="não autorizada"):
        verificar_id_token("tok", client_id="cid")


def test_token_firebase_aceita_founder(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Recusado:
        status_code = 401

        def json(self) -> dict[str, str]:
            return {}

    def _app() -> object:
        return object()

    monkeypatch.setattr("monitoritcd.painel.auth.httpx.get", lambda *_a, **_k: _Recusado())
    monkeypatch.setattr("firebase_admin.get_app", _app)
    monkeypatch.setattr(
        "firebase_admin.auth.verify_id_token",
        lambda _t: {"email": EMAIL_PERMITIDO, "email_verified": True},
    )
    assert verificar_id_token("jwt-firebase", client_id="cid") == EMAIL_PERMITIDO


def test_token_google_aceita_founder(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {
                "aud": "cid",
                "email": EMAIL_PERMITIDO,
                "email_verified": "true",
            }

    monkeypatch.setattr("monitoritcd.painel.auth.httpx.get", lambda *a, **k: _Resp())
    assert verificar_id_token("tok", client_id="cid") == EMAIL_PERMITIDO


def _catalogo_minimo(tmp: Path) -> None:
    pasta = tmp / "sources" / "_federal"
    pasta.mkdir(parents=True)
    (pasta / "lexml.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "lexml-portal",
                "uf": "_federal",
                "nome": "LexML",
                "tipo": "jurisprudencia",
                "parser": "generic_html",
                "url": "https://www.lexml.gov.br/",
                "ativo": True,
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def test_incluir_selecionar_excluir_fonte(tmp_path: Path) -> None:
    _catalogo_minimo(tmp_path)
    itens = listar_fontes(tmp_path)
    assert any(i["id"] == "lexml-portal" for i in itens)
    item = incluir_fonte(
        fonte_id="op-sefaz-xx",
        uf="MG",
        nome="SEFAZ teste",
        url="https://www.fazenda.mg.gov.br/",
        raiz=tmp_path,
    )
    assert item["selecionada"] is True
    assert item["operador"] is True
    off = selecionar_fonte("op-sefaz-xx", False, raiz=tmp_path)
    assert off["selecionada"] is False
    excluir_fonte("op-sefaz-xx", raiz=tmp_path)
    assert all(i["id"] != "op-sefaz-xx" for i in listar_fontes(tmp_path))


def test_nao_exclui_catalogo(tmp_path: Path) -> None:
    _catalogo_minimo(tmp_path)
    with pytest.raises(Exception, match="só fontes incluídas"):
        excluir_fonte("lexml-portal", raiz=tmp_path)


def test_parametros_extras(tmp_path: Path) -> None:
    out = gravar_extras(tmp_path, ["termo-novo-itcd", "termo-novo-itcd", ""])
    assert out["extras"] == ["termo-novo-itcd"]
    assert "termo-novo-itcd" in out["efetivos"]
    assert listar_parametros(tmp_path)["extras"] == ["termo-novo-itcd"]


def test_http_raiz_e_api_exigem_sessao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "development")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), PainelHandler)
    porta = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{porta}"
        home = httpx.get(f"{base}/", timeout=5)
        assert home.status_code == 200
        assert "Painel" in home.text or "MonitorITCD" in home.text
        fontes = httpx.get(f"{base}/api/fontes", timeout=5)
        assert fontes.status_code == 401
        assert "não autenticado" in fontes.json()["erro"]
        me = httpx.get(f"{base}/api/me", timeout=5)
        assert me.status_code == 200
        assert me.json()["ok"] is False
        assert me.json().get("hml_local") is True
        hml = httpx.post(f"{base}/api/auth/hml", json={}, timeout=5)
        assert hml.status_code == 200
        assert hml.json()["email"] == EMAIL_PERMITIDO
        cookie = hml.cookies.get("__session")
        assert cookie
        fontes_ok = httpx.get(
            f"{base}/api/fontes",
            cookies={"__session": cookie},
            timeout=5,
        )
        assert fontes_ok.status_code == 200
    finally:
        httpd.shutdown()


def test_ia_cadeia(tmp_path: Path) -> None:
    gravar_ia(
        tmp_path,
        [
            {
                "id": "gemini",
                "familia": "google",
                "habilitado": True,
                "modelo": "gemini-2.5-flash",
                "esforco": "alto",
            },
            {
                "id": "grok",
                "familia": "xai",
                "habilitado": False,
                "modelo": "grok-4",
                "esforco": "maximo",
            },
        ],
    )
    itens = listar_ia(tmp_path)
    assert [i["id"] for i in itens] == ["gemini", "grok"]
    assert itens[1]["habilitado"] is False
    assert itens[0]["esforco"] == "alto"


def _firebase_recusa(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Fb:
        @staticmethod
        def get_app() -> object:
            return object()

        class auth:
            @staticmethod
            def verify_id_token(_token: str) -> dict[str, str]:
                raise ValueError("jwt inválido")

    monkeypatch.setattr("firebase_admin.get_app", _Fb.get_app)
    monkeypatch.setattr("firebase_admin.auth.verify_id_token", _Fb.auth.verify_id_token)


def test_token_google_rejeita_entrada_invalida(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AuthPainelError, match="ausente"):
        verificar_id_token("", client_id="cid")

    def _boom(*_a: object, **_k: object) -> None:
        raise httpx.HTTPError("falha")

    _firebase_recusa(monkeypatch)
    monkeypatch.setattr("monitoritcd.painel.auth.httpx.get", _boom)
    with pytest.raises(AuthPainelError, match="Firebase recusado"):
        verificar_id_token("tok", client_id="cid")

    class _Recusado:
        status_code = 401

        def json(self) -> dict[str, str]:
            return {}

    monkeypatch.setattr("monitoritcd.painel.auth.httpx.get", lambda *_a, **_k: _Recusado())
    with pytest.raises(AuthPainelError, match="Firebase recusado"):
        verificar_id_token("tok", client_id="cid")

    class _Aud:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {"aud": "outro", "email": EMAIL_PERMITIDO, "email_verified": "true"}

    monkeypatch.setattr("monitoritcd.painel.auth.httpx.get", lambda *_a, **_k: _Aud())
    with pytest.raises(AuthPainelError, match="audience"):
        verificar_id_token("tok", client_id="cid")

    class _NaoVerificado:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {"aud": "cid", "email": EMAIL_PERMITIDO, "email_verified": "false"}

    monkeypatch.setattr("monitoritcd.painel.auth.httpx.get", lambda *_a, **_k: _NaoVerificado())
    with pytest.raises(AuthPainelError, match="não verificado"):
        verificar_id_token("tok", client_id="cid")


def test_sessao_e_json_invalidos() -> None:
    assert ler_sessao("a|b", "s") is None
    assert ler_sessao("a|x|mac", "s") is None
    assert parse_json_body(b"") == {}
    assert parse_json_body(b'{"a": 1}') == {"a": 1}
    with pytest.raises(ValueError, match="objeto"):
        parse_json_body(b"[1]")


def test_fonte_rejeita_path_traversal_e_uf_invalida(tmp_path: Path) -> None:
    _catalogo_minimo(tmp_path)
    with pytest.raises(SourceConfigError, match="id inválido"):
        excluir_fonte("../etc/passwd", raiz=tmp_path)
    with pytest.raises(SourceConfigError, match="id inválido"):
        incluir_fonte(
            fonte_id="../x",
            uf="MG",
            nome="x",
            url="https://www.fazenda.mg.gov.br/",
            raiz=tmp_path,
        )
    with pytest.raises(SourceConfigError, match="UF inválida"):
        incluir_fonte(
            fonte_id="op-sefaz-yy",
            uf="XX",
            nome="x",
            url="https://www.fazenda.mg.gov.br/",
            raiz=tmp_path,
        )
    with pytest.raises(SourceConfigError, match="desconhecida"):
        selecionar_fonte("nao-existe", True, raiz=tmp_path)
    (tmp_path / "config" / "painel").mkdir(parents=True)
    (tmp_path / "config" / "painel" / "fontes_selecao.json").write_text("[]", encoding="utf-8")
    assert listar_fontes(tmp_path)


def test_fonte_parser_invalido_e_duplicado(tmp_path: Path) -> None:
    _catalogo_minimo(tmp_path)
    with pytest.raises(SourceConfigError, match="parser ou tipo"):
        incluir_fonte(
            fonte_id="op-sefaz-zz",
            uf="MG",
            nome="x",
            url="https://www.fazenda.mg.gov.br/",
            parser="nao-existe",
            raiz=tmp_path,
        )
    incluir_fonte(
        fonte_id="op-sefaz-zz",
        uf="MG",
        nome="x",
        url="https://www.fazenda.mg.gov.br/",
        raiz=tmp_path,
    )
    with pytest.raises(SourceConfigError, match="duplicado"):
        incluir_fonte(
            fonte_id="op-sefaz-zz",
            uf="MG",
            nome="x",
            url="https://www.fazenda.mg.gov.br/",
            raiz=tmp_path,
        )


def test_ia_catalogo_e_padrao(tmp_path: Path) -> None:
    cat = catalogo_ia()
    assert "google" in cat["familias"]
    assert listar_ia(tmp_path)[0]["id"] == "gemini"
    (tmp_path / "config" / "painel").mkdir(parents=True)
    (tmp_path / "config" / "painel" / "ia-provedores.json").write_text("{}", encoding="utf-8")
    assert listar_ia(tmp_path)[0]["familia"] == "google"
    gravados = gravar_ia(
        tmp_path,
        [
            {"familia": "nao-existe", "modelo": "x"},
            {"familia": "ollama", "modelo": "desconhecido", "esforco": "absurdo"},
        ],
    )
    assert [i["familia"] for i in gravados] == ["ollama"]
    assert gravados[0]["modelo"] == "qwen2.5-coder:7b"
    assert gravados[0]["esforco"] == "medio"


def test_http_fluxo_hml_e_apis(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _catalogo_minimo(tmp_path)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("MONITORITCD_ROOT", str(tmp_path))
    monkeypatch.setenv("PAINEL_SESSION_SECRET", "segredo-teste-hml")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid-teste")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), PainelHandler)
    porta = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{porta}"
        assert httpx.post(f"{base}/nao-json", content=b"{", timeout=5).status_code == 400
        assert httpx.get(f"{base}/api/parametros", timeout=5).status_code == 401
        assert httpx.get(f"{base}/api/ia", timeout=5).status_code == 401
        assert httpx.get(f"{base}/api/nao", timeout=5).status_code == 404
        hml = httpx.post(f"{base}/api/auth/hml", json={}, timeout=5)
        assert hml.status_code == 200
        cookie = hml.cookies.get("__session")
        assert cookie
        ck = {"__session": cookie}
        assert httpx.get(f"{base}/api/me", cookies=ck, timeout=5).json()["email"] == EMAIL_PERMITIDO
        assert httpx.get(f"{base}/api/parametros", cookies=ck, timeout=5).status_code == 200
        ia = httpx.get(f"{base}/api/ia", cookies=ck, timeout=5)
        assert ia.status_code == 200
        assert "catalogo" in ia.json()
        inc = httpx.post(
            f"{base}/api/fontes/incluir",
            cookies=ck,
            json={
                "id": "op-http-mg",
                "uf": "MG",
                "nome": "SEFAZ HTTP",
                "url": "https://www.fazenda.mg.gov.br/",
            },
            timeout=5,
        )
        assert inc.status_code == 200
        sel = httpx.post(
            f"{base}/api/fontes/selecionar",
            cookies=ck,
            json={"id": "op-http-mg", "selecionada": False},
            timeout=5,
        )
        assert sel.status_code == 200
        assert sel.json()["item"]["selecionada"] is False
        par = httpx.post(
            f"{base}/api/parametros",
            cookies=ck,
            json={"extras": ["termo-hml"]},
            timeout=5,
        )
        assert par.status_code == 200
        assert "termo-hml" in par.json()["extras"]
        ia_g = httpx.post(
            f"{base}/api/ia",
            cookies=ck,
            json={"itens": [{"familia": "google", "habilitado": True}]},
            timeout=5,
        )
        assert ia_g.status_code == 200
        col = httpx.post(
            f"{base}/api/coleta",
            cookies=ck,
            json={"dry_run": True, "source_id": "lexml-portal"},
            timeout=5,
        )
        assert col.status_code == 200
        assert col.json()["aceito"] is True
        assert (
            httpx.post(
                f"{base}/api/parametros", cookies=ck, json={"extras": "x"}, timeout=5
            ).status_code
            == 400
        )
        assert (
            httpx.post(f"{base}/api/ia", cookies=ck, json={"itens": {}}, timeout=5).status_code
            == 400
        )
        assert (
            httpx.post(
                f"{base}/api/fontes/excluir", cookies=ck, json={"id": "op-http-mg"}, timeout=5
            ).status_code
            == 200
        )
        assert (
            httpx.post(f"{base}/api/inexistente", cookies=ck, json={}, timeout=5).status_code == 404
        )
        sair = httpx.post(f"{base}/api/auth/sair", json={}, timeout=5)
        assert sair.status_code == 200
    finally:
        httpd.shutdown()


def test_http_hml_recusa_producao_e_google_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _catalogo_minimo(tmp_path)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("MONITORITCD_ROOT", str(tmp_path))
    monkeypatch.setenv("PAINEL_SESSION_SECRET", "segredo-teste-hml")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), PainelHandler)
    porta = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{porta}"
        recusa = httpx.post(f"{base}/api/auth/hml", json={}, timeout=5)
        assert recusa.status_code == 403

        class _Resp:
            status_code = 200

            def json(self) -> dict[str, str]:
                return {
                    "aud": "cid",
                    "email": EMAIL_PERMITIDO,
                    "email_verified": "true",
                }

        monkeypatch.setattr("monitoritcd.painel.auth.httpx.get", lambda *_a, **_k: _Resp())
        google = httpx.post(f"{base}/api/auth/google", json={"id_token": "tok"}, timeout=5)
        assert google.status_code == 200
        assert google.json()["email"] == EMAIL_PERMITIDO
        ruim = httpx.post(f"{base}/api/auth/google", json={"id_token": ""}, timeout=5)
        assert ruim.status_code == 403
    finally:
        httpd.shutdown()
