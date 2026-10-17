import os
import time
from typing import Any, List, Optional
from google import genai
from google.genai import types

DYNAMIC_FALLBACK_CHAIN: List[str] = [
    "gemini-pro-latest",
    "gemini-flash-latest",
]


class GeminiAutoClient:
    """
    Cliente Google GenAI com descoberta dinamica de modelos e fallback automatico.
    Nao requer configuracao manual de nome de modelo.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=resolved_key) if resolved_key else genai.Client()
        self._cached_models: List[str] = []
        self._last_fetch: float = 0.0
        self._cache_ttl: float = 3600.0

    def discover_available_models(self, force_refresh: bool = False) -> List[str]:
        now = time.time()
        if not force_refresh and self._cached_models and (now - self._last_fetch < self._cache_ttl):
            return self._cached_models

        discovered: List[str] = []
        try:
            for model in self.client.models.list():
                raw_name = getattr(model, "name", "") or ""
                name = raw_name.replace("models/", "")
                actions = getattr(model, "supported_actions", None) or []

                is_gemini = name.startswith("gemini-")
                is_text_capable = not any(
                    excluded in name
                    for excluded in ("embedding", "imagen", "veo", "aqa", "tts", "audio")
                )
                supports_generate = len(actions) == 0 or "generateContent" in actions

                if is_gemini and is_text_capable and supports_generate:
                    discovered.append(name)

            if discovered:
                discovered.sort(reverse=True)
                combined = discovered + [m for m in DYNAMIC_FALLBACK_CHAIN if m not in discovered]
                self._cached_models = combined
                self._last_fetch = now
                return self._cached_models
        except Exception:
            pass

        self._cached_models = list(DYNAMIC_FALLBACK_CHAIN)
        self._last_fetch = now
        return self._cached_models

    def get_available_model(self) -> str:
        """Retorna automaticamente o melhor modelo disponivel no momento."""
        models = self.discover_available_models()
        return models[0]

    def generate_content(
        self,
        contents: Any,
        config: Optional[types.GenerateContentConfig] = None,
    ) -> types.GenerateContentResponse:
        """Executa generate_content selecionando e alternando o modelo automaticamente se necessario."""
        models = self.discover_available_models()
        last_error: Optional[Exception] = None

        for model_name in models:
            try:
                return self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                last_error = exc
                msg = str(exc).lower()
                recoverable = any(
                    token in msg
                    for token in ("404", "not found", "deprecated", "429", "quota", "503", "unavailable")
                )
                if not recoverable:
                    raise exc

        raise RuntimeError(f"Nenhum modelo disponivel respondeu com sucesso. Ultimo erro: {last_error}")
