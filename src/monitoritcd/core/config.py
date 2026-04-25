"""Configuração da aplicação via variáveis de ambiente.

Usa pydantic-settings com `SecretStr` — Princípio Canônico 3 (CLAUDE.md):
secrets PROIBIDOS em código fonte; sempre via env var ou GitHub Secrets.

`__repr__`/`__str__` mascaram campos sensíveis para evitar vazamento em logs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import EmailStr, Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from monitoritcd.core import limits


class Settings(BaseSettings):
    """Configurações carregadas de `.env` ou variáveis de ambiente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Owner (single-user)
    # ─────────────────────────────────────────────────────────────────────
    OWNER_ID: Annotated[str, Field(min_length=1, max_length=limits.MAX_OWNER_ID_LENGTH)]
    OWNER_EMAIL: EmailStr

    # ─────────────────────────────────────────────────────────────────────
    # LLM
    # ─────────────────────────────────────────────────────────────────────
    GEMINI_API_KEY: SecretStr
    GROQ_API_KEY: SecretStr | None = None

    # ─────────────────────────────────────────────────────────────────────
    # E-mail
    # ─────────────────────────────────────────────────────────────────────
    GMAIL_USER: EmailStr
    GMAIL_APP_PASSWORD: SecretStr

    # ─────────────────────────────────────────────────────────────────────
    # Telegram
    # ─────────────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: SecretStr
    TELEGRAM_OWNER_CHAT_ID: int
    TELEGRAM_WEBHOOK_SECRET: SecretStr

    # ─────────────────────────────────────────────────────────────────────
    # Firebase
    # ─────────────────────────────────────────────────────────────────────
    FIREBASE_PROJECT_ID: Annotated[str, Field(min_length=1, max_length=64)]
    FIREBASE_STORAGE_BUCKET: Annotated[str, Field(min_length=1, max_length=128)]
    FIREBASE_SERVICE_ACCOUNT_JSON: SecretStr

    # ─────────────────────────────────────────────────────────────────────
    # Observabilidade
    # ─────────────────────────────────────────────────────────────────────
    HEALTHCHECKS_URL: HttpUrl | None = None

    # ─────────────────────────────────────────────────────────────────────
    # Backup
    # ─────────────────────────────────────────────────────────────────────
    AGE_PUBLIC_KEY: str | None = None
    GDRIVE_FOLDER_ID: str | None = None

    # ─────────────────────────────────────────────────────────────────────
    # Runtime
    # ─────────────────────────────────────────────────────────────────────
    LOG_LEVEL: Annotated[str, Field(pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")] = "INFO"
    DRY_RUN: bool = False
    ENV: Annotated[str, Field(pattern=r"^(development|test|production)$")] = "development"

    def __repr__(self) -> str:
        """Mascarar tudo exceto identificadores não-sensíveis."""
        return (
            f"Settings("
            f"OWNER_ID={self.OWNER_ID!r}, "
            f"OWNER_EMAIL={self.OWNER_EMAIL!r}, "
            f"GMAIL_USER={self.GMAIL_USER!r}, "
            f"FIREBASE_PROJECT_ID={self.FIREBASE_PROJECT_ID!r}, "
            f"ENV={self.ENV!r}, "
            f"LOG_LEVEL={self.LOG_LEVEL!r}, "
            f"DRY_RUN={self.DRY_RUN}, "
            f"<<secrets redacted>>"
            f")"
        )

    def __str__(self) -> str:
        return self.__repr__()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância singleton de Settings (cache).

    Mypy não enxerga que pydantic-settings popula campos via env vars.
    O `type: ignore[call-arg]` é necessário e está documentado.
    """
    return Settings()  # type: ignore[call-arg]
