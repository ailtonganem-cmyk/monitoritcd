"""Configuração da aplicação via variáveis de ambiente.

Usa pydantic-settings com `SecretStr` — Princípio Canônico 3 (CLAUDE.md):
secrets PROIBIDOS em código fonte; sempre via env var ou GitHub Secrets.

`__repr__`/`__str__` mascaram campos sensíveis para evitar vazamento em logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from pydantic import EmailStr, Field, HttpUrl, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from monitoritcd.core import limits

COMO_CONFIGURAR = (
    "Defina os valores em GitHub → Settings → Secrets and variables → Actions "
    "(execução em CI) ou no arquivo .env local (modelo em .env.example)."
)

AVISO_EMAIL_DESABILITADO = (
    "Canal de e-mail DESABILITADO: GMAIL_USER e/ou GMAIL_APP_PASSWORD ausentes. "
    "A coleta, a gravação e o Telegram seguem funcionando normalmente. Para reativar "
    "o e-mail, defina GMAIL_USER (endereço remetente) e GMAIL_APP_PASSWORD "
    "(app password de 16 caracteres, gerado em "
    "https://myaccount.google.com/apppasswords). " + COMO_CONFIGURAR
)

# Campos opcionais: em GitHub Actions, um secret inexistente chega como string
# vazia, e "" precisa contar como ausente — não como valor presente e inválido.
CAMPOS_OPCIONAIS_EM_BRANCO = (
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "GROQ_API_KEY",
    "TELEGRAM_GROUP_CHAT_ID",
    "FIREBASE_SERVICE_ACCOUNT_JSON",
    "HEALTHCHECKS_URL",
    "PROXY_BR_URL",
    "PROXY_BR_TOKEN",
    "AGE_PUBLIC_KEY",
    "GDRIVE_FOLDER_ID",
)


class ConfiguracaoEssencialAusenteError(RuntimeError):
    """Credencial essencial ausente ou inválida — a coleta não pode prosseguir."""


class Settings(BaseSettings):
    """Configurações carregadas de `.env` ou variáveis de ambiente."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Owner (single-user) ────────────────────────────────────────────
    OWNER_ID: Annotated[str, Field(min_length=1, max_length=limits.MAX_OWNER_ID_LENGTH)]
    OWNER_EMAIL: EmailStr

    # ─────────────────────────────────────────────────────────────────────
    # LLM
    # ─────────────────────────────────────────────────────────────────────
    GEMINI_API_KEY: SecretStr
    GROQ_API_KEY: SecretStr | None = None

    # ─────────────────────────────────────────────────────────────────────
    # E-mail — canal OPCIONAL: sem credencial o pipeline roda e notifica só
    # pelo Telegram (a ausência de um canal não pode derrubar a coleta).
    # ─────────────────────────────────────────────────────────────────────
    GMAIL_USER: EmailStr | None = None
    GMAIL_APP_PASSWORD: SecretStr | None = None

    # ─────────────────────────────────────────────────────────────────────
    # Telegram
    # ─────────────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: SecretStr
    TELEGRAM_OWNER_CHAT_ID: int
    TELEGRAM_GROUP_CHAT_ID: int | None = None
    TELEGRAM_WEBHOOK_SECRET: SecretStr

    # ─────────────────────────────────────────────────────────────────────
    # Firebase
    # ─────────────────────────────────────────────────────────────────────
    FIREBASE_PROJECT_ID: Annotated[str, Field(min_length=1, max_length=64)]
    FIREBASE_STORAGE_BUCKET: Annotated[str, Field(min_length=1, max_length=128)]
    # Em Cloud Functions, credenciais vêm via Application Default Credentials
    # (metadata service GCP) — JSON explícito só é necessário em CI/local.
    FIREBASE_SERVICE_ACCOUNT_JSON: SecretStr | None = None

    # ─────────────────────────────────────────────────────────────────────
    # Observabilidade
    # ─────────────────────────────────────────────────────────────────────
    HEALTHCHECKS_URL: HttpUrl | None = None

    # ─────────────────────────────────────────────────────────────────────
    # Proxy BR (Cloud Function southamerica-east1) — fallback para fontes
    # geo-restringidas que GitHub runners US não acessam.
    # ─────────────────────────────────────────────────────────────────────
    PROXY_BR_URL: HttpUrl | None = None
    PROXY_BR_TOKEN: SecretStr | None = None

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

    @field_validator(*CAMPOS_OPCIONAIS_EM_BRANCO, mode="before")
    @classmethod
    def _branco_e_ausente(cls, valor: object) -> object:
        """Trata string vazia/em branco de campo opcional como ausente."""
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    @property
    def credenciais_email(self) -> tuple[str, SecretStr] | None:
        """Remetente e senha do canal de e-mail; `None` quando o canal está desligado."""
        if not self.GMAIL_USER or self.GMAIL_APP_PASSWORD is None:
            return None
        if not self.GMAIL_APP_PASSWORD.get_secret_value().strip():
            return None
        return str(self.GMAIL_USER), self.GMAIL_APP_PASSWORD

    @property
    def email_habilitado(self) -> bool:
        """Indica se há credencial suficiente para enviar e-mail."""
        return self.credenciais_email is not None

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


@dataclass(frozen=True)
class DiagnosticoConfiguracao:
    """Canais de notificação disponíveis nesta configuração."""

    canais_ativos: tuple[str, ...]
    canais_desabilitados: tuple[str, ...]
    avisos: tuple[str, ...]


def diagnosticar_configuracao(settings: Settings) -> DiagnosticoConfiguracao:
    """Lista canais ativos/desligados e o motivo acionável de cada desligamento."""
    ativos = ["telegram"]
    desabilitados: list[str] = []
    avisos: list[str] = []

    if settings.email_habilitado:
        ativos.append("email")
    else:
        desabilitados.append("email")
        avisos.append(AVISO_EMAIL_DESABILITADO)

    return DiagnosticoConfiguracao(
        canais_ativos=tuple(ativos),
        canais_desabilitados=tuple(desabilitados),
        avisos=tuple(avisos),
    )


def mensagem_configuracao_invalida(erro: ValidationError) -> str:
    """Formata o erro de validação sem ecoar valores — o input pode ser um secret."""
    detalhes = sorted(
        {
            f"{'.'.join(str(parte) for parte in err['loc']) or '(raiz)'}: {err['msg']}"
            for err in erro.errors()
        }
    )
    linhas = "\n".join(f"  - {d}" for d in detalhes)
    return (
        "Configuração essencial ausente ou inválida — a coleta não pode prosseguir.\n"
        f"{linhas}\n{COMO_CONFIGURAR}"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância singleton de Settings (cache).

    Mypy não enxerga que pydantic-settings popula campos via env vars.
    O `type: ignore[call-arg]` é necessário e está documentado.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as erro:
        # `from None`: o ValidationError original carrega os valores recebidos e
        # não pode chegar ao log de CI.
        raise ConfiguracaoEssencialAusenteError(mensagem_configuracao_invalida(erro)) from None
