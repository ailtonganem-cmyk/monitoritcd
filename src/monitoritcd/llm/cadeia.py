"""Monta a cadeia LLM a partir do painel + chaves de ambiente."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from monitoritcd.llm.fallback import CadeiaLLMProvider
from monitoritcd.llm.gemini import GeminiProvider
from monitoritcd.llm.groq import GroqProvider
from monitoritcd.llm.openai_compat import AnthropicProvider, OpenAICompatProvider
from monitoritcd.painel.ia_provedores import listar as listar_ia

if TYPE_CHECKING:
    from monitoritcd.core.config import Settings
    from monitoritcd.filters.llm_classifier import LLMProvider

logger = structlog.get_logger(__name__)


def _raiz() -> Path:
    env = os.environ.get("MONITORITCD_ROOT", "").strip()
    return Path(env) if env else Path(__file__).resolve().parents[3]


def _chave(settings: Settings, nome: str) -> Any:  # noqa: ANN401
    valor = getattr(settings, nome, None)
    if valor is None:
        return None
    raw = valor.get_secret_value() if hasattr(valor, "get_secret_value") else str(valor)
    if not str(raw).strip():
        return None
    return valor


def _instanciar(item: dict[str, Any], settings: Settings) -> LLMProvider | None:  # noqa: PLR0911,PLR0912
    familia = item.get("familia")
    modelo = str(item.get("modelo") or "")
    if familia == "google":
        key = _chave(settings, "GEMINI_API_KEY")
        return GeminiProvider(key, modelo) if key else None
    if familia == "groq":
        key = _chave(settings, "GROQ_API_KEY")
        return GroqProvider(key, modelo) if key else None
    if familia == "openai":
        key = _chave(settings, "OPENAI_API_KEY")
        if not key:
            return None
        return OpenAICompatProvider(
            key, modelo, endpoint="https://api.openai.com/v1/chat/completions", name=modelo
        )
    if familia == "xai":
        key = _chave(settings, "XAI_API_KEY")
        if not key:
            return None
        return OpenAICompatProvider(
            key, modelo, endpoint="https://api.x.ai/v1/chat/completions", name=modelo
        )
    if familia == "anthropic":
        key = _chave(settings, "ANTHROPIC_API_KEY")
        return AnthropicProvider(key, modelo) if key else None
    if familia == "openrouter":
        key = _chave(settings, "OPENROUTER_API_KEY")
        if not key:
            return None
        return OpenAICompatProvider(
            key,
            modelo,
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            name=f"openrouter:{modelo}",
            extra_headers={"HTTP-Referer": "https://monitoritcd.web.app", "X-Title": "MonitorITCD"},
        )
    if familia == "deepseek":
        key = _chave(settings, "DEEPSEEK_API_KEY")
        if not key:
            return None
        return OpenAICompatProvider(
            key,
            modelo,
            endpoint="https://api.deepseek.com/v1/chat/completions",
            name=f"deepseek:{modelo}",
        )
    if familia == "ollama":
        base = getattr(settings, "OLLAMA_BASE_URL", None) or "http://127.0.0.1:11434"
        endpoint = str(base).rstrip("/") + "/v1/chat/completions"
        try:
            return OpenAICompatProvider(
                None, modelo, endpoint=endpoint, name=f"ollama:{modelo}", exigir_loopback=True
            )
        except ValueError:
            logger.warning("llm.ollama_recusado_host")
            return None
    return None


def montar_cadeia(settings: Settings) -> LLMProvider | None:
    """Provedores habilitados do painel que tiverem chave. None = usar default Gemini/Groq."""
    itens = [i for i in listar_ia(_raiz()) if i.get("habilitado")]
    provedores: list[LLMProvider] = []
    for item in itens:
        inst = _instanciar(item, settings)
        if inst is None:
            logger.info(
                "llm.provedor_pulado",
                familia=item.get("familia"),
                id=item.get("id"),
            )
            continue
        provedores.append(inst)
    if not provedores:
        return None
    if len(provedores) == 1:
        return provedores[0]
    return CadeiaLLMProvider(provedores)
