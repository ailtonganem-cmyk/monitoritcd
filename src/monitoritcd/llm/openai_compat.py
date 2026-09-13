"""Provedor OpenAI-compatible (OpenAI, xAI, Ollama). Chave só via SecretStr."""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
import structlog

from monitoritcd.core import limits
from monitoritcd.filters.llm_classifier import SYSTEM_PROMPT

if TYPE_CHECKING:
    from pydantic import SecretStr

logger = structlog.get_logger(__name__)


class OpenAICompatProvider:
    """Chat completions JSON — timeout e parse iguais ao Groq."""

    def __init__(
        self,
        api_key: SecretStr | None,
        model: str,
        *,
        endpoint: str,
        name: str,
        extra_headers: dict[str, str] | None = None,
        exigir_loopback: bool = False,
    ) -> None:
        self._api_key = api_key
        self._model_name = model
        self._endpoint = endpoint
        self.name = name
        self._extra = extra_headers or {}
        if exigir_loopback:
            host = (urlparse(endpoint).hostname or "").lower()
            if host not in {"127.0.0.1", "localhost", "::1"}:
                msg = f"ollama recusado fora de loopback: {host}"
                raise ValueError(msg)

    async def classify_batch(
        self,
        items_text: list[str],
        *,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        if not items_text:
            return []
        items_block = "[\n" + ",\n".join(items_text) + "\n]"
        user_msg = (
            f"Classifique os {len(items_text)} itens abaixo. "
            f"Retorne JSON com chave 'items' contendo lista de objetos.\n\n{items_block}"
        )
        sys_p = system_prompt if system_prompt is not None else SYSTEM_PROMPT
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": user_msg},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        headers = {"Content-Type": "application/json", **self._extra}
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(limits.LLM_TIMEOUT_SECONDS)) as client:
            response = await asyncio.wait_for(
                client.post(self._endpoint, json=payload, headers=headers),
                timeout=limits.LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        if not text:
            raise ValueError("provedor retornou resposta vazia")
        return _parse_lista(text, expected=len(items_text))


class AnthropicProvider:
    """Anthropic Messages API — chave só via SecretStr."""

    def __init__(self, api_key: SecretStr, model: str) -> None:
        self._api_key = api_key
        self._model_name = model
        self.name = model

    async def classify_batch(
        self,
        items_text: list[str],
        *,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        if not items_text:
            return []
        items_block = "[\n" + ",\n".join(items_text) + "\n]"
        user_msg = (
            f"Classifique os {len(items_text)} itens. "
            f"Retorne JSON com chave items.\n\n{items_block}"
        )
        sys_p = system_prompt if system_prompt is not None else SYSTEM_PROMPT
        headers = {
            "x-api-key": self._api_key.get_secret_value(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self._model_name,
            "max_tokens": 4096,
            "system": sys_p,
            "messages": [{"role": "user", "content": user_msg}],
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(limits.LLM_TIMEOUT_SECONDS)) as client:
            response = await asyncio.wait_for(
                client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers),
                timeout=limits.LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        blocos = response.json().get("content") or []
        text = "".join(b.get("text", "") for b in blocos if isinstance(b, dict))
        if not text:
            raise ValueError("Anthropic retornou resposta vazia")
        return _parse_lista(text, expected=len(items_text))


def _parse_lista(text: str, expected: int) -> list[dict[str, Any]]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    parsed = json.loads(cleaned)
    if isinstance(parsed, dict):
        for key in ("items", "results", "classifications", "list"):
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break
    if not isinstance(parsed, list):
        raise ValueError(f"tipo inesperado: {type(parsed).__name__}")
    if len(parsed) != expected:
        raise ValueError(f"{len(parsed)} respostas, esperado {expected}")
    return parsed
