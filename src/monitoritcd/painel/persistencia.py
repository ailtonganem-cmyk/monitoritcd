"""Persistência do painel: arquivos locais (HML) ou Firestore (produção)."""

from __future__ import annotations

import json
import os
from pathlib import Path  # noqa: TC003
from typing import Any

COLLECTION = "monitor_painel_config"


def usar_firestore() -> bool:
    """Produção Firebase grava overlay no Firestore; HML continua em disco."""
    if os.environ.get("PAINEL_STORE", "").strip().lower() == "firestore":
        return True
    if os.environ.get("PAINEL_STORE", "").strip().lower() == "files":
        return False
    return os.environ.get("ENV", "development") == "production"


def _client():  # noqa: ANN202
    from google.cloud.firestore import Client  # noqa: PLC0415

    projeto = os.environ.get("FIREBASE_PROJECT_ID", "").strip() or None
    return Client(project=projeto)


def ler_json(raiz: Path, nome: str) -> dict[str, Any]:
    if usar_firestore():
        snap = _client().collection(COLLECTION).document(nome).get()
        dados = snap.to_dict() if snap.exists else None
        return dict(dados) if isinstance(dados, dict) else {}
    path = raiz / "config" / "painel" / nome
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def gravar_json(raiz: Path, nome: str, dados: dict[str, Any]) -> None:
    if usar_firestore():
        _client().collection(COLLECTION).document(nome).set(dados)
        return
    pasta = raiz / "config" / "painel"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_text(
        json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def ler_operador_yamls(raiz: Path) -> dict[str, str]:
    """id → texto YAML das fontes criadas no painel."""
    if usar_firestore():
        snap = _client().collection(COLLECTION).document("fontes_operador").get()
        dados = snap.to_dict() if snap.exists else None
        if not isinstance(dados, dict):
            return {}
        return {str(k): str(v) for k, v in dados.items() if isinstance(v, str)}
    pasta = raiz / "sources" / "_operador"
    out: dict[str, str] = {}
    if not pasta.is_dir():
        return out
    for candidato in pasta.iterdir():
        if candidato.suffix == ".yaml" and candidato.is_file():
            out[candidato.stem] = candidato.read_text(encoding="utf-8")
    return out


def gravar_operador_yaml(raiz: Path, sid: str, texto: str) -> None:
    if usar_firestore():
        ref = _client().collection(COLLECTION).document("fontes_operador")
        ref.set({sid: texto}, merge=True)
        return
    pasta = raiz / "sources" / "_operador"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{sid}.yaml").write_text(texto, encoding="utf-8")


def apagar_operador_yaml(raiz: Path, sid: str) -> bool:
    if usar_firestore():
        ref = _client().collection(COLLECTION).document("fontes_operador")
        snap = ref.get()
        dados = snap.to_dict() if snap.exists else None
        if not isinstance(dados, dict) or sid not in dados:
            return False
        from google.cloud.firestore import DELETE_FIELD  # noqa: PLC0415

        ref.update({sid: DELETE_FIELD})
        return True
    pasta = raiz / "sources" / "_operador"
    alvo = pasta / f"{sid}.yaml"
    if not alvo.is_file():
        return False
    alvo.unlink()
    return True


def materializar_operador(raiz: Path) -> None:
    """Espelha YAMLs do Firestore em disco para o loader da pipeline."""
    if not usar_firestore():
        return
    pasta = raiz / "sources" / "_operador"
    pasta.mkdir(parents=True, exist_ok=True)
    for sid, texto in ler_operador_yamls(raiz).items():
        (pasta / f"{sid}.yaml").write_text(texto, encoding="utf-8")
