"""Persistência do painel em arquivos (HML)."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest  # noqa: TC002

from monitoritcd.painel.persistencia import (
    apagar_operador_yaml,
    gravar_json,
    gravar_operador_yaml,
    ler_json,
    ler_operador_yamls,
    materializar_operador,
    usar_firestore,
)


def test_usar_firestore_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAINEL_STORE", "files")
    monkeypatch.setenv("ENV", "production")
    assert usar_firestore() is False
    monkeypatch.setenv("PAINEL_STORE", "firestore")
    assert usar_firestore() is True
    monkeypatch.delenv("PAINEL_STORE", raising=False)
    monkeypatch.setenv("ENV", "development")
    assert usar_firestore() is False
    monkeypatch.setenv("ENV", "production")
    assert usar_firestore() is True


def test_json_e_operador_em_disco(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAINEL_STORE", "files")
    gravar_json(tmp_path, "fontes_selecao.json", {"lexml-portal": True})
    assert ler_json(tmp_path, "fontes_selecao.json")["lexml-portal"] is True
    gravar_operador_yaml(tmp_path, "minha-fonte", "id: minha-fonte\n")
    yamls = ler_operador_yamls(tmp_path)
    assert "minha-fonte" in yamls
    assert apagar_operador_yaml(tmp_path, "minha-fonte") is True
    assert "minha-fonte" not in ler_operador_yamls(tmp_path)
    materializar_operador(tmp_path)  # no-op em files
