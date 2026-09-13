"""Cadeia LLM do painel e recusa de Ollama fora do loopback."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any

import pytest

from monitoritcd.llm.fallback import CadeiaLLMProvider, LLMProvidersExhaustedError
from monitoritcd.llm.openai_compat import OpenAICompatProvider
from monitoritcd.painel.ia_provedores import gravar as gravar_ia


class _Stub:
    def __init__(self, name: str, responses: list[Any]) -> None:
        self.name = name
        self._responses = responses
        self.calls = 0

    async def classify_batch(
        self, items_text: list[str], *, system_prompt: str | None = None
    ) -> list[dict[str, Any]]:
        idx = self.calls
        self.calls += 1
        resp = self._responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return resp


@pytest.mark.asyncio
async def test_cadeia_quota_passa_ao_proximo() -> None:
    a = _Stub("a", [Exception("429 quota")])
    b = _Stub("b", [[{"ok": True}]])
    cadeia = CadeiaLLMProvider([a, b])
    out = await cadeia.classify_batch(["x"])
    assert out == [{"ok": True}]
    assert a.calls == 1
    assert b.calls == 1


@pytest.mark.asyncio
async def test_cadeia_esgotada() -> None:
    a = _Stub("a", [Exception("429")])
    b = _Stub("b", [Exception("RESOURCE_EXHAUSTED")])
    with pytest.raises(LLMProvidersExhaustedError):
        await CadeiaLLMProvider([a, b]).classify_batch(["x"])


def test_ollama_recusa_host_remoto() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OpenAICompatProvider(
            None,
            "qwen",
            endpoint="https://evil.example/v1/chat/completions",
            name="ollama",
            exigir_loopback=True,
        )


def test_gravar_ia_nao_guarda_chave(tmp_path: Path) -> None:
    raiz = tmp_path
    itens = gravar_ia(
        raiz,
        [
            {
                "id": "g",
                "familia": "google",
                "habilitado": True,
                "modelo": "gemini-2.5-flash",
                "segredo_proibido": "nao-gravar",
            }
        ],
    )
    assert "api_key" not in itens[0]
    texto = (raiz / "config" / "painel" / "ia-provedores.json").read_text(encoding="utf-8")
    assert "SEGREDO" not in texto
