"""Provedores de LLM (Gemini primary, Groq fallback)."""

from __future__ import annotations

from monitoritcd.llm.fake import FakeLLMProvider
from monitoritcd.llm.gemini import GeminiProvider

__all__ = ["FakeLLMProvider", "GeminiProvider"]
