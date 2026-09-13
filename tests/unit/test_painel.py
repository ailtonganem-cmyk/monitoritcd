"""Painel local: auth allowlist, fontes operador, parâmetros e IA."""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path  # noqa: TC003

import httpx
import pytest
import yaml

from monitoritcd.painel import EMAIL_PERMITIDO
from monitoritcd.painel.auth import AuthPainelError, emitir_sessao, ler_sessao, verificar_id_token
from monitoritcd.painel.fontes import excluir_fonte, incluir_fonte, listar_fontes, selecionar_fonte
from monitoritcd.painel.http import PainelHandler
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
        assert me.status_code == 401
        assert me.json().get("hml_local") is True
        hml = httpx.post(f"{base}/api/auth/hml", json={}, timeout=5)
        assert hml.status_code == 200
        assert hml.json()["email"] == EMAIL_PERMITIDO
        cookie = hml.cookies.get("monitoritcd_painel")
        assert cookie
        fontes_ok = httpx.get(
            f"{base}/api/fontes",
            cookies={"monitoritcd_painel": cookie},
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
