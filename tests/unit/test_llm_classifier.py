"""Testes do classifier LLM (sem chamadas reais).

Usa fake provider que retorna respostas pré-definidas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from monitoritcd.core.models import RawItem, SeverityTier, TipoAto
from monitoritcd.filters.llm_classifier import (
    PROMPT_VERSION,
    build_item_text,
    classify_with_provider,
    map_relevancia_to_tier,
    parse_llm_response,
)

NOW = datetime.now(UTC)


def _raw(titulo: str = "PL 1234/2026 — ITCMD") -> RawItem:
    return RawItem(
        source_id="x",
        titulo_raw=titulo,
        url="https://x.gov.br/i",
        fetched_at=NOW,
        content_hash="a" * 64,
    )


class _FakeProvider:
    """Mock provider que retorna respostas determinísticas."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.call_count = 0

    async def classify_batch(self, items_text: list[str]) -> list[dict[str, Any]]:
        self.call_count += 1
        return self.responses[: len(items_text)]


class _FailingProvider:
    """Provider que falha sempre."""

    def __init__(self) -> None:
        self.call_count = 0

    async def classify_batch(self, items_text: list[str]) -> list[dict[str, Any]]:
        self.call_count += 1
        return [{"invalid": "schema"}]  # falta campos obrigatórios


@pytest.mark.unit
class TestMapRelevanciaToTier:
    def test_critico(self) -> None:
        assert map_relevancia_to_tier(10) == SeverityTier.CRITICO
        assert map_relevancia_to_tier(9) == SeverityTier.CRITICO

    def test_alta(self) -> None:
        assert map_relevancia_to_tier(8) == SeverityTier.ALTA

    def test_normal(self) -> None:
        assert map_relevancia_to_tier(7) == SeverityTier.NORMAL

    def test_baixa(self) -> None:
        assert map_relevancia_to_tier(5) == SeverityTier.BAIXA
        assert map_relevancia_to_tier(6) == SeverityTier.BAIXA

    def test_descartado(self) -> None:
        assert map_relevancia_to_tier(0) == SeverityTier.DESCARTADO
        assert map_relevancia_to_tier(4) == SeverityTier.DESCARTADO


@pytest.mark.unit
class TestBuildItemText:
    def test_includes_context_delimiter(self) -> None:
        item = _raw()
        text = build_item_text(item)
        assert "<context>" in text
        assert "</context>" in text
        assert item.titulo_raw in text

    def test_truncates_long_text(self) -> None:
        long = "a" * 5000
        item = RawItem(
            source_id="x",
            titulo_raw="t",
            url="https://x.gov.br/",
            texto_raw=long,
            fetched_at=NOW,
            content_hash="a" * 64,
        )
        text = build_item_text(item)
        assert len(text) < 4000


@pytest.mark.unit
class TestParseLLMResponse:
    def test_valid_response(self) -> None:
        resp = {
            "tipo": "projeto_lei",
            "relevancia": 8,
            "resumo": "PL sobre ITCMD",
            "numero_ato": "1234/2026",
            "orgao_emissor": "ALESP",
            "tags": ["itcmd", "sp"],
        }
        result = parse_llm_response(resp, llm_model="gemini-1.5-flash")
        assert result.tipo == TipoAto.PROJETO_LEI
        assert result.relevancia == 8
        assert result.severity_tier == SeverityTier.ALTA
        assert result.metadados_extraidos["numero_ato"] == "1234/2026"
        assert result.llm_prompt_version == PROMPT_VERSION

    def test_missing_resumo_raises(self) -> None:
        with pytest.raises(ValueError, match="resumo"):
            parse_llm_response({"tipo": "outro", "relevancia": 5}, llm_model="x")

    def test_invalid_tipo_falls_to_outro(self) -> None:
        resp = {"tipo": "nao_existe", "relevancia": 5, "resumo": "x"}
        result = parse_llm_response(resp, llm_model="x")
        assert result.tipo == TipoAto.OUTRO

    def test_relevancia_clamped_to_max(self) -> None:
        resp = {"tipo": "outro", "relevancia": 999, "resumo": "x"}
        result = parse_llm_response(resp, llm_model="x")
        assert result.relevancia == 10

    def test_relevancia_clamped_to_min(self) -> None:
        resp = {"tipo": "outro", "relevancia": -5, "resumo": "x"}
        result = parse_llm_response(resp, llm_model="x")
        assert result.relevancia == 0

    def test_extra_tags_truncated(self) -> None:
        resp = {
            "tipo": "outro",
            "relevancia": 5,
            "resumo": "x",
            "tags": [f"tag{i}" for i in range(50)],
        }
        result = parse_llm_response(resp, llm_model="x")
        assert len(result.tags) <= 20  # MAX_TAGS_PER_DOC


@pytest.mark.unit
class TestClassifyWithProvider:
    @pytest.mark.asyncio
    async def test_classifies_batch(self) -> None:
        provider = _FakeProvider(
            [
                {"tipo": "projeto_lei", "relevancia": 8, "resumo": "Resumo 1"},
                {"tipo": "decreto", "relevancia": 6, "resumo": "Resumo 2"},
            ],
        )
        items = [_raw("Item 1"), _raw("Item 2")]
        results = await classify_with_provider(items, provider, llm_model="gemini-test")
        assert len(results) == 2
        assert results[0].relevancia == 8
        assert results[1].tipo == TipoAto.DECRETO

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self) -> None:
        results = await classify_with_provider([], _FakeProvider([]), llm_model="x")
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_too_large_raises(self) -> None:
        items = [_raw(f"i{i}") for i in range(20)]
        with pytest.raises(ValueError, match="MAX_BATCH_LLM"):
            await classify_with_provider(items, _FakeProvider([]), llm_model="x")

    @pytest.mark.asyncio
    async def test_count_mismatch_raises(self) -> None:
        # Provider retorna 1 quando esperava 2
        provider = _FakeProvider(
            [{"tipo": "outro", "relevancia": 5, "resumo": "x"}],
        )
        items = [_raw("a"), _raw("b")]
        with pytest.raises(ValueError):
            await classify_with_provider(items, provider, llm_model="x")

    @pytest.mark.asyncio
    async def test_invalid_response_retries_then_fails(self) -> None:
        provider = _FailingProvider()
        with pytest.raises(ValueError):
            await classify_with_provider([_raw()], provider, llm_model="x")
        # tenacity tenta 3 vezes (limits.RETRY_MAX_ATTEMPTS)
        assert provider.call_count == 3

    @pytest.mark.asyncio
    async def test_non_dict_response_raises(self) -> None:
        provider = _FakeProvider([])
        # Sobrescreve para retornar lista vazia mesmo
        provider.responses = ["not-a-dict"]  # type: ignore[list-item]
        with pytest.raises(ValueError):
            await classify_with_provider([_raw()], provider, llm_model="x")
