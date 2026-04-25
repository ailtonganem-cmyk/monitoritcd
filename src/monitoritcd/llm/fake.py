"""Provedor LLM fake — para testes e --dry-run.

Retorna classificações determinísticas baseadas em heurísticas simples.
Não chama API real. Usado em CI e desenvolvimento.
"""

from __future__ import annotations

from typing import Any

from monitoritcd.filters.keywords import detect_topics
from monitoritcd.filters.llm_classifier import map_relevancia_to_tier  # noqa: F401


class FakeLLMProvider:
    """Provider que classifica via heurísticas (sem chamada externa)."""

    name: str = "fake-llm"

    async def classify_batch(self, items_text: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for text in items_text:
            topics = detect_topics(text) or [
                __import__("monitoritcd.core.models", fromlist=["Topic"]).Topic.ITCD
            ]
            # Score baseado em quantidade de tópicos detectados (1-3 → 5-8)
            relevancia = min(10, 4 + len(topics) * 2)
            results.append(
                {
                    "tipo": "noticia",
                    "topics": [t.value for t in topics],
                    "relevancia": relevancia,
                    "resumo": text[:200].replace("<context>", "").replace("</context>", "").strip(),
                    "numero_ato": None,
                    "orgao_emissor": None,
                    "tags": [t.value for t in topics],
                },
            )
        return results
