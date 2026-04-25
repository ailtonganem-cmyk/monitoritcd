"""Provedor LLM Gemini 2.5 Flash via google-genai SDK.

Princípios canônicos aplicados:
1. **API key via SecretStr** — nunca exposta em logs.
2. **Timeout** via `LLM_TIMEOUT_SECONDS`.
3. **JSON mode** para reduzir hallucination de formato.
4. **Output validado por pydantic** no caller (`llm_classifier.parse_llm_response`).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

import structlog

from monitoritcd.core import limits
from monitoritcd.filters.llm_classifier import SYSTEM_PROMPT

if TYPE_CHECKING:
    from pydantic import SecretStr

logger = structlog.get_logger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider:
    """Provedor Gemini para classificação batch."""

    name: str = DEFAULT_MODEL

    def __init__(self, api_key: SecretStr, model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model_name = model
        self._client: Any = None  # google.genai.Client lazy-init

    def _ensure_client(self) -> Any:  # noqa: ANN401
        if self._client is not None:
            return self._client
        try:
            from google import genai  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover
            msg = "google-genai não instalado: pip install google-genai"
            raise RuntimeError(msg) from e
        self._client = genai.Client(api_key=self._api_key.get_secret_value())
        return self._client

    async def classify_batch(self, items_text: list[str]) -> list[dict[str, Any]]:
        """Envia batch ao Gemini, retorna lista de dicts.

        Os items são separados por `---ITEM---` no prompt; o LLM retorna JSON array.
        """
        if not items_text:
            return []

        items_block = "\n\n---ITEM---\n\n".join(items_text)
        prompt = (
            f"{SYSTEM_PROMPT}\n\nClassifique os {len(items_text)} itens abaixo:\n\n{items_block}"
        )

        client = self._ensure_client()

        # Roda síncrono em thread (google-genai sync API)
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=self._model_name,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            ),
            timeout=limits.LLM_TIMEOUT_SECONDS,
        )

        text = response.text
        if not text:
            msg = "Gemini retornou resposta vazia"
            raise ValueError(msg)

        return self._parse_response(text, expected=len(items_text))

    @staticmethod
    def _parse_response(text: str, expected: int) -> list[dict[str, Any]]:
        """Parseia JSON do Gemini, tolerando wrappers comuns."""
        # Remove ```json ... ``` se aparecer (alguns modelos teimam)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            msg = f"Gemini retornou JSON inválido: {e}"
            raise ValueError(msg) from e

        if isinstance(parsed, dict) and "items" in parsed:
            parsed = parsed["items"]

        if not isinstance(parsed, list):
            msg = f"Gemini retornou tipo inesperado: {type(parsed).__name__}"
            raise ValueError(msg)

        if len(parsed) != expected:
            msg = f"Gemini retornou {len(parsed)} respostas, esperado {expected}"
            raise ValueError(msg)

        return parsed
