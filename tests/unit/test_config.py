"""Testes de `core.config`.

Cobre:
- SecretStr mascara valores em repr()/str()
- Validação de campos obrigatórios
- LOG_LEVEL e ENV são restritos a valores válidos
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from monitoritcd.core.config import Settings


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

    def test_required_field_missing_raises(self) -> None:
        kwargs = _valid_kwargs()
        del kwargs["OWNER_ID"]
        with pytest.raises(ValidationError, match="OWNER_ID"):
            Settings(**kwargs)  # type: ignore[arg-type]

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
