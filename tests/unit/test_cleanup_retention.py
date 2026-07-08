"""Testes de `scripts/cleanup_retention.py`.

Cobre `_dt_to_stored` — helper duplicado do equivalente em
`monitoritcd.storage.firestore_store` (script standalone, sem importar o
pacote `monitoritcd` — ver docstring da função). Mesmo bug de fundo: os
campos `original.fetched_at` / `timestamp` / `started_at` são gravados como
STRING pelo pydantic; comparar contra um `datetime` Python direto no
`.where(...)` nunca casa no Firestore, então o cleanup nunca purgava nada,
silenciosamente.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "cleanup_retention.py"


def _load_module():  # type: ignore[no-untyped-def]
    """Carrega `cleanup_retention.py` como módulo (não está em src/)."""
    spec = importlib.util.spec_from_file_location("cleanup_retention", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cleanup_retention"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cr():  # type: ignore[no-untyped-def]
    return _load_module()


@pytest.mark.unit
class TestDtToStored:
    def test_com_microssegundos(self, cr) -> None:  # type: ignore[no-untyped-def]
        value = datetime(2026, 4, 26, 13, 4, 34, 304171, tzinfo=UTC)
        assert cr._dt_to_stored(value) == "2026-04-26T13:04:34.304171Z"

    def test_sem_microssegundos_emite_seis_digitos_zero(self, cr) -> None:  # type: ignore[no-untyped-def]
        value = datetime(2026, 4, 26, 13, 4, 34, 0, tzinfo=UTC)
        assert cr._dt_to_stored(value) == "2026-04-26T13:04:34.000000Z"

    def test_naive_assume_utc(self, cr) -> None:  # type: ignore[no-untyped-def]
        naive = datetime(2026, 4, 26, 13, 4, 34, 304171)  # noqa: DTZ001 — teste explícito de naive
        aware = datetime(2026, 4, 26, 13, 4, 34, 304171, tzinfo=UTC)
        assert cr._dt_to_stored(naive) == cr._dt_to_stored(aware)


@pytest.mark.unit
class TestCleanupUsaStringNosWhere:
    def test_where_recebe_string_nao_datetime(self, cr, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        calls: list[tuple[str, str, object]] = []

        class FakeQuery:
            def where(self, field: str, op: str, value: object) -> FakeQuery:
                calls.append((field, op, value))
                return self

            def limit(self, _n: int) -> FakeQuery:
                return self

            def stream(self):  # type: ignore[no-untyped-def]
                return []

        class FakeClient:
            def collection(self, _name: str) -> FakeQuery:
                return FakeQuery()

        # `Client` é importado localmente dentro de `cleanup()` via
        # `from google.cloud.firestore import Client` — substituir no
        # módulo real de origem para que o import local resolva o fake.
        import google.cloud.firestore as gcf  # noqa: PLC0415

        monkeypatch.setattr(gcf, "Client", FakeClient)

        cr.cleanup(dry_run=True)

        assert all(isinstance(value, str) for _field, _op, value in calls)
        fields = {field for field, _op, _value in calls}
        assert fields == {"llm.severity_tier", "original.fetched_at", "timestamp", "started_at"}
