"""Testes de `core.config`.

Cobre:
- SecretStr mascara valores em repr()/str()
- Validação de campos obrigatórios
- LOG_LEVEL e ENV são restritos a valores válidos
- Canal de e-mail opcional (ausente/vazio) e diagnóstico de canais
- Falha acionável e sem vazamento quando falta credencial essencial
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, EmailStr, SecretStr, ValidationError

from monitoritcd.core import config as config_mod
from monitoritcd.core.config import (
    ConfiguracaoEssencialAusenteError,
    Settings,
    diagnosticar_configuracao,
)


def _valid_kwargs() -> dict[str, str | int]:
    return {
        "OWNER_ID": "owner-alpha",
        "OWNER_EMAIL": "owner@example.com",
        "GEMINI_API_KEY": "gemini-key-fake",
        "GMAIL_USER": "owner@gmail.com",
        "GMAIL_APP_PASSWORD": "abcdefghijklmnop",
        "TELEGRAM_BOT_TOKEN": "1234567890:fakeFAKE_token_12345",
        "TELEGRAM_OWNER_CHAT_ID": 12345678,
        "TELEGRAM_WEBHOOK_SECRET": "webhook-secret-fake",
        "FIREBASE_PROJECT_ID": "monitoritcd",
        "FIREBASE_STORAGE_BUCKET": "monitoritcd.appspot.com",
        "FIREBASE_SERVICE_ACCOUNT_JSON": '{"type":"service_account"}',
    }


@pytest.mark.unit
class TestSettings:
    def test_valid_settings_loads(self) -> None:
        settings = Settings(**_valid_kwargs())  # type: ignore[arg-type]
        assert settings.OWNER_ID == "owner-alpha"
        assert isinstance(settings.GEMINI_API_KEY, SecretStr)
        assert settings.LOG_LEVEL == "INFO"
        assert settings.ENV == "development"

    def test_repr_masks_secrets(self) -> None:
        settings = Settings(**_valid_kwargs())  # type: ignore[arg-type]
        rep = repr(settings)
        assert "fakeFAKE_token" not in rep
        assert "webhook-secret-fake" not in rep
        assert "secrets redacted" in rep
        assert settings.OWNER_ID in rep  # ID não-sensível pode aparecer

    def test_str_masks_secrets(self) -> None:
        settings = Settings(**_valid_kwargs())  # type: ignore[arg-type]
        s = str(settings)
        assert "fakeFAKE_token" not in s

    def test_secret_str_get_value(self) -> None:
        settings = Settings(**_valid_kwargs())  # type: ignore[arg-type]
        # Acesso explícito via .get_secret_value() funciona
        assert settings.GEMINI_API_KEY.get_secret_value() == "gemini-key-fake"

    def test_log_level_pattern_enforced(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["LOG_LEVEL"] = "VERBOSE"  # inválido
        with pytest.raises(ValidationError):
            Settings(**kwargs)  # type: ignore[arg-type]

    def test_env_pattern_enforced(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["ENV"] = "staging"  # inválido (só dev/test/production)
        with pytest.raises(ValidationError):
            Settings(**kwargs)  # type: ignore[arg-type]

    def test_required_field_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # `_env_file=None` + delenv: sem isso o teste passa em CI e falha na
        # máquina do dono, onde o `.env` supre o campo removido.
        monkeypatch.delenv("OWNER_ID", raising=False)
        kwargs = _valid_kwargs()
        del kwargs["OWNER_ID"]
        with pytest.raises(ValidationError, match="OWNER_ID"):
            Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]

    def test_owner_email_must_be_valid(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["OWNER_EMAIL"] = "not-an-email"
        with pytest.raises(ValidationError):
            Settings(**kwargs)  # type: ignore[arg-type]

    def test_dry_run_default_false(self) -> None:
        settings = Settings(**_valid_kwargs())  # type: ignore[arg-type]
        assert settings.DRY_RUN is False

    def test_telegram_group_chat_id_defaults_to_none(self) -> None:
        settings = Settings(**_valid_kwargs())  # type: ignore[arg-type]
        assert settings.TELEGRAM_GROUP_CHAT_ID is None

    def test_telegram_group_chat_id_accepts_explicit_value(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["TELEGRAM_GROUP_CHAT_ID"] = -1001234567890
        settings = Settings(**kwargs)  # type: ignore[arg-type]
        assert settings.TELEGRAM_GROUP_CHAT_ID == -1001234567890


def _settings_isolado(**overrides: object) -> Settings:
    """Settings sem ler o `.env` local — determinismo entre máquinas."""
    kwargs: dict[str, object] = {**_valid_kwargs(), **overrides}
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
class TestCanalEmailOpcional:
    def test_ausencia_de_gmail_nao_bloqueia_configuracao(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GMAIL_USER", raising=False)
        monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
        kwargs = _valid_kwargs()
        del kwargs["GMAIL_USER"]
        del kwargs["GMAIL_APP_PASSWORD"]

        settings = Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]

        assert settings.GMAIL_USER is None
        assert settings.GMAIL_APP_PASSWORD is None
        assert settings.email_habilitado is False
        assert settings.credenciais_email is None

    def test_gmail_vazio_conta_como_ausente(self) -> None:
        # Secret inexistente no GitHub Actions chega como "" — foi exatamente
        # o input_value='' que derrubou 25 execuções.
        settings = _settings_isolado(GMAIL_USER="", GMAIL_APP_PASSWORD="")

        assert settings.GMAIL_USER is None
        assert settings.GMAIL_APP_PASSWORD is None
        assert settings.email_habilitado is False

    def test_gmail_so_com_espacos_conta_como_ausente(self) -> None:
        settings = _settings_isolado(GMAIL_USER="   ", GMAIL_APP_PASSWORD="  ")  # noqa: S106
        assert settings.email_habilitado is False

    def test_senha_em_branco_desliga_canal_mesmo_com_usuario(self) -> None:
        # `SecretStr` não passa pelo validador de string em branco: quem barra
        # a senha vazia aqui é o guard de `credenciais_email`.
        settings = _settings_isolado(
            GMAIL_USER="bot@example.com",
            GMAIL_APP_PASSWORD=SecretStr("   "),
        )
        assert settings.email_habilitado is False
        assert settings.credenciais_email is None

    def test_credenciais_completas_habilitam_canal(self) -> None:
        settings = _settings_isolado(
            GMAIL_USER="bot@example.com",
            GMAIL_APP_PASSWORD="abcdefghijklmnop",  # noqa: S106
        )
        assert settings.email_habilitado is True
        credenciais = settings.credenciais_email
        assert credenciais is not None
        remetente, senha = credenciais
        assert remetente == "bot@example.com"
        assert senha.get_secret_value() == "abcdefghijklmnop"

    def test_opcional_vazio_vira_none_nos_demais_campos(self) -> None:
        settings = _settings_isolado(GROQ_API_KEY="", HEALTHCHECKS_URL="", PROXY_BR_URL="")
        assert settings.GROQ_API_KEY is None
        assert settings.HEALTHCHECKS_URL is None
        assert settings.PROXY_BR_URL is None


@pytest.mark.unit
class TestDiagnosticoConfiguracao:
    def test_sem_email_reporta_canal_desabilitado_com_aviso(self) -> None:
        diagnostico = diagnosticar_configuracao(_settings_isolado(GMAIL_USER=""))

        assert diagnostico.canais_ativos == ("telegram",)
        assert diagnostico.canais_desabilitados == ("email",)
        assert len(diagnostico.avisos) == 1
        assert "GMAIL_USER" in diagnostico.avisos[0]
        assert "DESABILITADO" in diagnostico.avisos[0]

    def test_com_email_reporta_dois_canais_sem_aviso(self) -> None:
        diagnostico = diagnosticar_configuracao(_settings_isolado())

        assert diagnostico.canais_ativos == ("telegram", "email")
        assert diagnostico.canais_desabilitados == ()
        assert diagnostico.avisos == ()


class _ModeloExigente(BaseModel):
    FIREBASE_PROJECT_ID: str


class _ModeloComEmail(BaseModel):
    GMAIL_USER: EmailStr


@pytest.mark.unit
class TestFalhaEssencialAcionavel:
    def test_credencial_essencial_ausente_gera_mensagem_acionavel(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(config_mod, "Settings", _ModeloExigente)
        config_mod.get_settings.cache_clear()
        try:
            with pytest.raises(ConfiguracaoEssencialAusenteError) as exc:
                config_mod.get_settings()
        finally:
            config_mod.get_settings.cache_clear()

        mensagem = str(exc.value)
        assert "FIREBASE_PROJECT_ID" in mensagem
        assert "Secrets" in mensagem
        assert ".env.example" in mensagem

    def test_mensagem_nao_vaza_valor_recebido(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        valor_sensivel = "valor-secreto-nao-deve-vazar"

        def _fabrica_invalida() -> _ModeloComEmail:
            return _ModeloComEmail(GMAIL_USER=valor_sensivel)

        monkeypatch.setattr(config_mod, "Settings", _fabrica_invalida)
        config_mod.get_settings.cache_clear()
        try:
            with pytest.raises(ConfiguracaoEssencialAusenteError) as exc:
                config_mod.get_settings()
        finally:
            config_mod.get_settings.cache_clear()

        assert valor_sensivel not in str(exc.value)
        # `from None`: o ValidationError original (que carrega o valor) não é encadeado.
        assert exc.value.__cause__ is None
