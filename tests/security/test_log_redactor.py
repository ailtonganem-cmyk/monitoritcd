"""Testes do redator de logs.

Garante que tokens conhecidos NUNCA passam pra logs.
Princípio canônico 3 (CLAUDE.md): secrets nunca expostos.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from monitoritcd.security.log_redactor import (
    SENSITIVE_KEYS,
    redact_sensitive,
)


@pytest.mark.security
class TestPatternRedaction:
    @pytest.mark.parametrize(
        ("token", "marker"),
        [
            ("sk_live_abcdefghij1234567890XYZ", "sk_live_***REDACTED***"),
            ("sk_test_abcdefghij1234567890XYZ", "sk_test_***REDACTED***"),
            ("whsec_abcdefghij1234567890XYZ", "whsec_***REDACTED***"),
            ("AIzaSyDfake1234567890123456789012345678", "AIza***REDACTED***"),
            ("ghp_abcdefghij1234567890XYZabcdefghij12", "ghp_***REDACTED***"),
        ],
    )
    def test_token_replaced(self, token: str, marker: str) -> None:
        event = {"msg": f"using {token} for auth"}
        result = redact_sensitive(None, "info", event)
        assert token not in result["msg"]
        assert marker in result["msg"]

    def test_telegram_token_redacted(self) -> None:
        token = "1234567890:ABCdefGHIjklmNOPqrsTUVwxyz0123456"  # noqa: S105 - test fixture
        event = {"msg": f"bot token: {token}"}
        result = redact_sensitive(None, "info", event)
        assert token not in result["msg"]
        assert "REDACTED-TELEGRAM-TOKEN" in result["msg"]

    def test_aws_key_redacted(self) -> None:
        event = {"msg": "AWS key AKIAIOSFODNN7EXAMPLE in config"}
        result = redact_sensitive(None, "info", event)
        assert "AKIAIOSFODNN7EXAMPLE" not in result["msg"]

    def test_private_key_block_redacted(self) -> None:
        pk = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
        event = {"data": pk}
        result = redact_sensitive(None, "info", event)
        # As linhas internas devem ser substituídas
        assert "MIIEpAIBAAKCAQEA" not in result["data"]
        assert "REDACTED-PRIVATE-KEY" in result["data"]


@pytest.mark.security
class TestSensitiveKeyRedaction:
    @pytest.mark.parametrize("key", list(SENSITIVE_KEYS))
    def test_sensitive_keys_value_fully_redacted(self, key: str) -> None:
        event = {key: "any-value-at-all"}
        result = redact_sensitive(None, "info", event)
        assert result[key] == "***REDACTED***"

    def test_password_redacted_regardless_of_value(self) -> None:
        event = {"password": "hello"}
        result = redact_sensitive(None, "info", event)
        assert result["password"] == "***REDACTED***"  # noqa: S105 - test assertion

    def test_case_insensitive_key_match(self) -> None:
        event = {"Authorization": "Bearer abc"}
        result = redact_sensitive(None, "info", event)
        assert result["Authorization"] == "***REDACTED***"

    def test_normal_keys_pass_through(self) -> None:
        event = {"username": "alice", "request_id": "abc-123"}
        result = redact_sensitive(None, "info", event)
        assert result["username"] == "alice"
        assert result["request_id"] == "abc-123"


@pytest.mark.security
class TestNestedRedaction:
    def test_nested_dict_redacted(self) -> None:
        event = {
            "request": {
                "headers": {
                    "authorization": "Bearer secret",
                    "host": "example.com",
                },
            },
        }
        result = redact_sensitive(None, "info", event)
        assert result["request"]["headers"]["authorization"] == "***REDACTED***"
        assert result["request"]["headers"]["host"] == "example.com"

    def test_list_of_strings_redacted(self) -> None:
        event = {"messages": ["normal msg", "leaked AIzaSyDfakekey1234567890123456789012345"]}
        result = redact_sensitive(None, "info", event)
        assert "AIzaSyDfakekey1234567890123456789012345" not in str(result)


@pytest.mark.security
class TestBearerToken:
    def test_bearer_redacted(self) -> None:
        event = {"msg": "header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"}
        result = redact_sensitive(None, "info", event)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result["msg"]


@pytest.mark.security
class TestPropertyBased:
    @given(st.dictionaries(st.text(max_size=20), st.text(max_size=200), max_size=10))
    def test_never_crashes_on_arbitrary_dict(self, event: dict[str, str]) -> None:
        result = redact_sensitive(None, "info", event)
        assert isinstance(result, dict)
