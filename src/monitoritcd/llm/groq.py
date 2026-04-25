"""Provedor LLM Groq (Llama 3.3 70B) — fallback quando Gemini estoura quota.

Groq oferece API compatível OpenAI com llama-3.3-70b-versatile gratuita
(rate limits generosos: 30 RPM, 14400 TPM). Usado como fallback automático
quando Gemini retorna 429 RESOURCE_EXHAUSTED.

Princípios canônicos aplicados:
1. **API key via SecretStr** — nunca exposta em logs.
2. **Timeout** via `LLM_TIMEOUT_SECONDS`.
3. **JSON mode** via `response_format`.
4. **Output validado por pydantic** no caller.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from monitoritcd.core import limits
from monitoritcd.filters.llm_classifier import SYSTEM_PROMPT

if TYPE_CHECKING:
    from pydantic import SecretStr

logger = structlog.get_logger(__name__)

DEFAULT_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    """Provedor Groq para classificação batch (fallback de Gemini)."""

    name: str = DEFAULT_MODEL

    def __init__(self, api_key: SecretStr, model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model_name = model

    async def classify_batch(self, items_text: list[str]) -> list[dict[str, Any]]:
        """Envia batch ao Groq via OpenAI-compatible API."""
        if not items_text:
            return []

        items_block = "\n\n---ITEM---\n\n".join(items_text)
        user_msg = (
            f"Classifique os {len(items_text)} itens abaixo. "
            f"Retorne JSON com chave 'items' contendo lista de objetos.\n\n{items_block}"
        )

        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(limits.LLM_TIMEOUT_SECONDS)) as client:
            response = await asyncio.wait_for(
                client.post(GROQ_API_URL, json=payload, headers=headers),
                timeout=limits.LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

        data = response.json()
        text = data["choices"][0]["message"]["content"]
        if not text:
            msg = "Groq retornou resposta vazia"
            raise ValueError(msg)

        return self._parse_response(text, expected=len(items_text))

    @staticmethod
    def _parse_response(text: str, expected: int) -> list[dict[str, Any]]:
        """Parseia JSON do Groq, tolerando wrappers e chave items/results."""
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            msg = f"Groq retornou JSON inválido: {e}"
            raise ValueError(msg) from e

        if isinstance(parsed, dict):
            for key in ("items", "results", "classifications", "list"):
                if key in parsed and isinstance(parsed[key], list):
                    parsed = parsed[key]
                    break

        if not isinstance(parsed, list):
            msg = f"Groq retornou tipo inesperado: {type(parsed).__name__}"
            raise ValueError(msg)

        if len(parsed) != expected:
            msg = f"Groq retornou {len(parsed)} respostas, esperado {expected}"
            raise ValueError(msg)

        return parsed
