"""Cadeia de provedores de IA — metadado local, no estilo ColetorImoveisMG."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003
from typing import Any

FAMILIAS = ("google", "groq", "openai", "anthropic", "xai", "ollama", "openrouter", "deepseek")
ESFORCOS = ("baixo", "medio", "alto", "extra-alto", "maximo")
MODELOS: dict[str, list[str]] = {
    "google": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-5-mini", "gpt-5"],
    "anthropic": ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-1"],
    "xai": ["grok-4", "grok-4-fast", "grok-3-mini"],
    "ollama": ["qwen2.5-coder:7b", "gemma4:26b"],
    "openrouter": ["openai/gpt-4o-mini", "google/gemini-2.5-flash", "anthropic/claude-sonnet-4.5"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
}
ARQUIVO = "ia-provedores.json"


def _path(raiz: Path) -> Path:
    return raiz / "config" / "painel" / ARQUIVO


def catalogo() -> dict[str, Any]:
    return {
        "familias": list(FAMILIAS),
        "esforcos": list(ESFORCOS),
        "modelos": {k: list(v) for k, v in MODELOS.items()},
        "modelo_padrao": {k: v[0] for k, v in MODELOS.items()},
        "esforco_padrao": "medio",
    }


def _padrao() -> list[dict[str, Any]]:
    return [
        {
            "id": "gemini",
            "familia": "google",
            "habilitado": True,
            "modelo": MODELOS["google"][0],
            "esforco": "medio",
            "ordem": 1,
        },
        {
            "id": "groq",
            "familia": "groq",
            "habilitado": True,
            "modelo": MODELOS["groq"][0],
            "esforco": "medio",
            "ordem": 2,
        },
    ]


def listar(raiz: Path) -> list[dict[str, Any]]:
    from monitoritcd.painel.persistencia import ler_json, usar_firestore  # noqa: PLC0415

    if usar_firestore():
        data = ler_json(raiz, ARQUIVO)
    else:
        path = _path(raiz)
        if not path.is_file():
            return _padrao()
        data = json.loads(path.read_text(encoding="utf-8"))
    itens = data.get("itens")
    if not isinstance(itens, list):
        return _padrao()
    return sorted(itens, key=lambda i: int(i.get("ordem", 99)))


def gravar(raiz: Path, itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    limpos: list[dict[str, Any]] = []
    for idx, bruto in enumerate(itens, start=1):
        familia = str(bruto.get("familia") or "")
        if familia not in FAMILIAS:
            continue
        esforco = str(bruto.get("esforco") or "medio")
        if esforco not in ESFORCOS:
            esforco = "medio"
        modelos = MODELOS[familia]
        modelo = str(bruto.get("modelo") or modelos[0])
        if modelo not in modelos:
            modelo = modelos[0]
        limpos.append(
            {
                "id": str(bruto.get("id") or f"{familia}-{idx}"),
                "familia": familia,
                "habilitado": bool(bruto.get("habilitado", True)),
                "modelo": modelo,
                "esforco": esforco,
                "ordem": idx,
            }
        )
    from monitoritcd.painel.persistencia import gravar_json  # noqa: PLC0415

    gravar_json(raiz, ARQUIVO, {"itens": limpos})
    return listar(raiz)
