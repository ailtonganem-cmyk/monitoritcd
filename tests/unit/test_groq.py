"""Testes unitários do `llm/groq.py` (provedor fallback de LLM).

Cobre:
- classify_batch happy path (mock httpx via respx)
- classify_batch com lista vazia → []
- _parse_response: wrappers ```json```, chaves items/results/list
- Erros: JSON invalido, tipo inesperado, length mismatch, resposta vazia
- API key nao vaza em logs/repr
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import SecretStr

from monitoritcd.llm.groq import GROQ_API_URL, GroqProvider


def _provider() -> GroqProvider:
    return GroqProvider(api_key=SecretStr("gsk_fake_test_key_12345"))


def _mock_groq_response(content: str | dict | list, status: int = 200) -> httpx.Response:
    """Constroi resposta no formato OpenAI-compatible do Groq."""
    if isinstance(content, dict | list):
        content = json.dumps(content)
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": content}}]},
    )


@pytest.mark.unit
class TestClassifyBatch:
    """`classify_batch` envia POST e parseia resposta."""

    @pytest.mark.asyncio
    async def test_lista_vazia_retorna_vazia_sem_request(self) -> None:
        async with respx.mock:
            route = respx.post(GROQ_API_URL).mock()
            result = await _provider().classify_batch([])
        assert result == []
        assert not route.called  # otimizacao: sem itens = sem chamada

    @pytest.mark.asyncio
    async def test_happy_path_items_chave(self) -> None:
        async with respx.mock:
            respx.post(GROQ_API_URL).mock(
                return_value=_mock_groq_response(
                    {"items": [{"relevancia": 8, "tipo": "PL"}]},
                ),
            )
            result = await _provider().classify_batch(["item teste"])
        assert len(result) == 1
        assert result[0]["relevancia"] == 8
        assert result[0]["tipo"] == "PL"

    @pytest.mark.asyncio
    async def test_envia_authorization_header_e_modelo(self) -> None:
        async with respx.mock:
            route = respx.post(GROQ_API_URL).mock(
                return_value=_mock_groq_response({"items": [{"relevancia": 5}]}),
            )
            await _provider().classify_batch(["x"])
        assert route.called
        request = route.calls[0].request
        assert request.headers["Authorization"].startswith("Bearer ")
        body = json.loads(request.content)
        assert body["model"] == "llama-3.3-70b-versatile"
        assert body["response_format"] == {"type": "json_object"}
        assert len(body["messages"]) == 2  # system + user

    @pytest.mark.asyncio
    async def test_resposta_vazia_levanta(self) -> None:
        async with respx.mock:
            respx.post(GROQ_API_URL).mock(return_value=_mock_groq_response(""))
            with pytest.raises(ValueError, match="vazia"):
                await _provider().classify_batch(["item"])


@pytest.mark.unit
class TestParseResponse:
    """`_parse_response` aceita variantes comuns de output do LLM."""

    def test_wrapper_markdown_json_removido(self) -> None:
        text = '```json\n{"items": [{"r": 1}]}\n```'
        result = GroqProvider._parse_response(text, expected=1)
        assert result == [{"r": 1}]

    def test_wrapper_markdown_simples_removido(self) -> None:
        text = '```\n{"items": [{"r": 1}]}\n```'
        result = GroqProvider._parse_response(text, expected=1)
        assert result == [{"r": 1}]

    def test_chave_results_aceita(self) -> None:
        text = '{"results": [{"a": 1}, {"b": 2}]}'
        result = GroqProvider._parse_response(text, expected=2)
        assert len(result) == 2

    def test_chave_classifications_aceita(self) -> None:
        text = '{"classifications": [{"x": 1}]}'
        result = GroqProvider._parse_response(text, expected=1)
        assert result == [{"x": 1}]

    def test_chave_list_aceita(self) -> None:
        text = '{"list": [{"y": 2}]}'
        result = GroqProvider._parse_response(text, expected=1)
        assert result == [{"y": 2}]

    def test_lista_direta_aceita(self) -> None:
        text = '[{"a": 1}, {"b": 2}]'
        result = GroqProvider._parse_response(text, expected=2)
        assert len(result) == 2

    def test_json_invalido_levanta(self) -> None:
        with pytest.raises(ValueError, match="JSON inválido"):
            GroqProvider._parse_response("{not json", expected=1)

    def test_tipo_inesperado_levanta(self) -> None:
        # dict sem chave conhecida nem lista direta -> erro
        text = '{"unexpected_key": "value"}'
        with pytest.raises(ValueError, match="tipo inesperado"):
            GroqProvider._parse_response(text, expected=1)

    def test_length_mismatch_levanta(self) -> None:
        text = '{"items": [{"a": 1}]}'
        with pytest.raises(ValueError, match="esperado 2"):
            GroqProvider._parse_response(text, expected=2)


@pytest.mark.unit
class TestApiKeyMasking:
    """API key nunca vaza em logs/repr (princípio canonico 3)."""

    def test_repr_nao_expoe_key(self) -> None:
        p = GroqProvider(api_key=SecretStr("gsk_super_secret_12345"))
        # SecretStr ja mascara em repr; verificamos que nao aparece literal
        assert "gsk_super_secret_12345" not in repr(p._api_key)
        assert "gsk_super_secret_12345" not in str(p._api_key)
