"""Cadeia LLM do painel e recusa de Ollama fora do loopback."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from monitoritcd.llm.cadeia import _instanciar, montar_cadeia
from monitoritcd.llm.fallback import CadeiaLLMProvider, LLMProvidersExhaustedError
from monitoritcd.llm.openai_compat import AnthropicProvider, OpenAICompatProvider, _parse_lista
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
    assert "segredo_proibido" not in itens[0]
    texto = (raiz / "config" / "painel" / "ia-provedores.json").read_text(encoding="utf-8")
    assert "nao-gravar" not in texto


def test_cadeia_vazia_e_nome() -> None:
    with pytest.raises(ValueError, match="vazia"):
        CadeiaLLMProvider([])
    stub = _Stub("unico", [[{"ok": True}]])
    assert CadeiaLLMProvider([stub]).name == "unico"


class _Cfg:
    GEMINI_API_KEY = SecretStr("gemini-fake")
    GROQ_API_KEY = SecretStr("groq-fake")
    OPENAI_API_KEY = SecretStr("openai-fake")
    ANTHROPIC_API_KEY = SecretStr("anthropic-fake")
    XAI_API_KEY = SecretStr("xai-fake")
    OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def test_instanciar_familias() -> None:
    cfg = _Cfg()
    assert _instanciar({"familia": "google", "modelo": "gemini-2.5-flash"}, cfg) is not None
    assert _instanciar({"familia": "groq", "modelo": "llama-3.3-70b-versatile"}, cfg) is not None
    assert _instanciar({"familia": "openai", "modelo": "gpt-4o-mini"}, cfg) is not None
    assert _instanciar({"familia": "xai", "modelo": "grok-4"}, cfg) is not None
    assert _instanciar({"familia": "anthropic", "modelo": "claude-sonnet-4-5"}, cfg) is not None
    assert _instanciar({"familia": "ollama", "modelo": "qwen2.5-coder:7b"}, cfg) is not None
    assert _instanciar({"familia": "desconhecida", "modelo": "x"}, cfg) is None
    vazio = _Cfg()
    vazio.GEMINI_API_KEY = SecretStr("")
    vazio.OPENAI_API_KEY = None
    assert _instanciar({"familia": "google", "modelo": "gemini-2.5-flash"}, vazio) is None
    assert _instanciar({"familia": "openai", "modelo": "gpt-4o-mini"}, vazio) is None
    vazio.OLLAMA_BASE_URL = "https://evil.example"
    assert _instanciar({"familia": "ollama", "modelo": "qwen2.5-coder:7b"}, vazio) is None


def test_montar_cadeia_painel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MONITORITCD_ROOT", str(tmp_path))
    gravar_ia(
        tmp_path,
        [
            {"id": "g", "familia": "google", "habilitado": True, "modelo": "gemini-2.5-flash"},
            {"id": "q", "familia": "groq", "habilitado": True, "modelo": "llama-3.3-70b-versatile"},
            {"id": "off", "familia": "xai", "habilitado": False, "modelo": "grok-4"},
        ],
    )
    cadeia = montar_cadeia(_Cfg())  # type: ignore[arg-type]
    assert cadeia is not None
    assert "+" in cadeia.name or cadeia.name
    gravar_ia(tmp_path, [{"id": "off", "familia": "xai", "habilitado": False, "modelo": "grok-4"}])
    assert montar_cadeia(_Cfg()) is None  # type: ignore[arg-type]
    gravar_ia(
        tmp_path,
        [{"id": "g", "familia": "google", "habilitado": True, "modelo": "gemini-2.5-flash"}],
    )
    um = montar_cadeia(_Cfg())  # type: ignore[arg-type]
    assert um is not None
    assert "+" not in um.name


@pytest.mark.asyncio
async def test_openai_compat_e_anthropic() -> None:
    provedor = OpenAICompatProvider(
        SecretStr("sk-fake"),
        "gpt-4o-mini",
        endpoint="https://api.openai.com/v1/chat/completions",
        name="gpt-4o-mini",
    )
    assert await provedor.classify_batch([]) == []
    async with respx.mock:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps({"items": [{"ok": True}]})}}]},
            )
        )
        out = await provedor.classify_batch(["x"])
    assert out == [{"ok": True}]

    ant = AnthropicProvider(SecretStr("ant-fake"), "claude-sonnet-4-5")
    assert await ant.classify_batch([]) == []
    async with respx.mock:
        respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(
                200,
                json={"content": [{"type": "text", "text": json.dumps({"items": [{"ok": 1}]})}]},
            )
        )
        out_a = await ant.classify_batch(["y"])
    assert out_a == [{"ok": 1}]

    assert _parse_lista('```json\n{"results": [{"a": 1}]}\n```', 1) == [{"a": 1}]
    with pytest.raises(ValueError, match="inesperado"):
        _parse_lista('{"nope": 1}', 1)
    with pytest.raises(ValueError, match="esperado"):
        _parse_lista("[1, 2]", 1)
