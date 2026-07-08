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

    async def classify_batch(
        self,
        items_text: list[str],
        *,
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for text in items_text:
            topics = detect_topics(text)
            if not topics:
                results.append(
                    {
                        "relacionado": False,
                        "tipo": "outro",
                        "topics": [],
                        "relevancia": 0,
                        "resumo": "Item fora do escopo MonitorITCD.",
                        "resumo_completo": "",
                        "pontos_chave": [],
                        "motivo_relevancia": "Nenhum tópico canônico foi detectado.",
                        "contexto": "",
                        "assuntos_relacionados": [],
                        "numero_ato": None,
                        "orgao_emissor": None,
                        "tags": [],
                    },
                )
                continue
            # Score baseado em quantidade de tópicos detectados (1-3 → 5-8)
            relevancia = min(10, 4 + len(topics) * 2)
            resumo = text[:200].replace("<context>", "").replace("</context>", "").strip()
            results.append(
                {
                    "relacionado": True,
                    "tipo": "noticia",
                    "topics": [t.value for t in topics],
                    "relevancia": relevancia,
                    "resumo": resumo,
                    "resumo_completo": resumo,
                    "pontos_chave": [f"Tópico detectado: {t.value}" for t in topics],
                    "motivo_relevancia": "Item contém termos canônicos do MonitorITCD.",
                    "contexto": (
                        f"Contexto gerado por IA (fake): tópico {topics[0].value} "
                        "envolve regras já consolidadas na área; consulte a fonte "
                        "original para o texto integral."
                    ),
                    "assuntos_relacionados": [t.value for t in topics],
                    "numero_ato": None,
                    "orgao_emissor": None,
                    "tags": [t.value for t in topics],
                },
            )
        return results
