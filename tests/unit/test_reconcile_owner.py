"""Testes de `scripts/reconcile_owner.py`.

Cobre `assert_safe_project` (guard de allowlist) e `reconcile` (dry-run vs
--apply) — o script standalone que corrige `owner_id` de docs poluídos pelo
incidente 2026-07-09 (ver docstring do script e `orchestrator.py`).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "reconcile_owner.py"


def _load_module():  # type: ignore[no-untyped-def]
    """Carrega `reconcile_owner.py` como módulo (não está em src/)."""
    spec = importlib.util.spec_from_file_location("reconcile_owner", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reconcile_owner"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ro():  # type: ignore[no-untyped-def]
    return _load_module()


class FakeDocRef:
    def __init__(self, doc_id: str, updates: list[tuple[str, dict]]) -> None:  # type: ignore[no-untyped-def]
        self._doc_id = doc_id
        self._updates = updates

    def update(self, data: dict) -> None:  # type: ignore[no-untyped-def]
        self._updates.append((self._doc_id, data))


class FakeSnapshot:
    def __init__(self, doc_id: str, updates: list[tuple[str, dict]]) -> None:  # type: ignore[no-untyped-def]
        self.id = doc_id
        self.reference = FakeDocRef(doc_id, updates)


class FakeQuery:
    def __init__(self, doc_ids: list[str], updates: list[tuple[str, dict]]) -> None:  # type: ignore[no-untyped-def]
        self._doc_ids = doc_ids
        self._updates = updates
        self.wheres: list[tuple[str, str, object]] = []

    def where(self, field: str, op: str, value: object) -> FakeQuery:
        self.wheres.append((field, op, value))
        return self

    def stream(self):  # type: ignore[no-untyped-def]
        return [FakeSnapshot(doc_id, self._updates) for doc_id in self._doc_ids]


class FakeClient:
    def __init__(  # type: ignore[no-untyped-def]
        self,
        doc_ids: list[str],
        updates: list[tuple[str, dict]],
        *,
        project: str | None = None,
    ) -> None:
        self._doc_ids = doc_ids
        self._updates = updates
        self.project = project

    def collection(self, _name: str) -> FakeQuery:
        return FakeQuery(self._doc_ids, self._updates)


@pytest.mark.unit
class TestAssertSafeProject:
    def test_projeto_permitido_nao_levanta(self, ro) -> None:  # type: ignore[no-untyped-def]
        ro.assert_safe_project("sefworkstation-app")
        ro.assert_safe_project("sefworkstation-hml")

    def test_projeto_fora_da_allowlist_levanta(self, ro) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(ValueError, match="não permitido"):
            ro.assert_safe_project("outro-projeto-qualquer")


@pytest.mark.unit
class TestReconcileDryRun:
    def test_dry_run_nao_escreve(self, ro, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        updates: list[tuple[str, dict]] = []
        doc_ids = ["camara-deputados-proposicoes:aaa", "camara-deputados-proposicoes:bbb"]

        import google.cloud.firestore as gcf  # noqa: PLC0415

        monkeypatch.setattr(
            gcf, "Client", lambda **kw: FakeClient(doc_ids, updates, **kw)  # type: ignore[arg-type]
        )

        count = ro.reconcile(
            project="sefworkstation-app",
            owner_atual="sefworkstation-monitor-homolog",
            owner_canonico="ailton-ganem-monitor",
            apply=False,
        )

        assert count == 2
        assert updates == []

    def test_where_filtra_por_owner_atual(self, ro, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        updates: list[tuple[str, dict]] = []
        queries: list[FakeQuery] = []

        class TrackingClient(FakeClient):
            def collection(self, _name: str) -> FakeQuery:
                q = FakeQuery(self._doc_ids, self._updates)
                queries.append(q)
                return q

        import google.cloud.firestore as gcf  # noqa: PLC0415

        monkeypatch.setattr(
            gcf, "Client", lambda **kw: TrackingClient([], updates, **kw)  # type: ignore[arg-type]
        )

        ro.reconcile(
            project="sefworkstation-app",
            owner_atual="sefworkstation-monitor-homolog",
            owner_canonico="ailton-ganem-monitor",
            apply=False,
        )

        assert queries[0].wheres == [
            ("owner_id", "==", "sefworkstation-monitor-homolog")
        ]


@pytest.mark.unit
class TestReconcileApply:
    def test_apply_atualiza_so_owner_id_doc_a_doc(self, ro, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        updates: list[tuple[str, dict]] = []
        doc_ids = ["camara-deputados-proposicoes:aaa"]

        import google.cloud.firestore as gcf  # noqa: PLC0415

        monkeypatch.setattr(
            gcf, "Client", lambda **kw: FakeClient(doc_ids, updates, **kw)  # type: ignore[arg-type]
        )

        count = ro.reconcile(
            project="sefworkstation-app",
            owner_atual="sefworkstation-monitor-homolog",
            owner_canonico="ailton-ganem-monitor",
            apply=True,
        )

        assert count == 1
        assert updates == [
            ("camara-deputados-proposicoes:aaa", {"owner_id": "ailton-ganem-monitor"})
        ]

    def test_apply_idempotente_segunda_rodada_encontra_zero(self, ro, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        updates: list[tuple[str, dict]] = []

        import google.cloud.firestore as gcf  # noqa: PLC0415

        monkeypatch.setattr(
            gcf, "Client", lambda **kw: FakeClient([], updates, **kw)  # type: ignore[arg-type]
        )

        count = ro.reconcile(
            project="sefworkstation-app",
            owner_atual="sefworkstation-monitor-homolog",
            owner_canonico="ailton-ganem-monitor",
            apply=True,
        )

        assert count == 0


@pytest.mark.unit
class TestMainCli:
    def test_main_recusa_projeto_fora_da_allowlist(self, ro, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "reconcile_owner.py",
                "--project=projeto-invalido",
                "--owner-atual=a",
                "--owner-canonico=b",
            ],
        )
        exit_code = ro.main()
        assert exit_code == 1
        assert "não permitido" in capsys.readouterr().err

    def test_main_recusa_owners_iguais(self, ro, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "reconcile_owner.py",
                "--project=sefworkstation-app",
                "--owner-atual=mesmo",
                "--owner-canonico=mesmo",
            ],
        )
        exit_code = ro.main()
        assert exit_code == 1
        assert "iguais" in capsys.readouterr().err

    def test_main_dry_run_ok(self, ro, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        updates: list[tuple[str, dict]] = []

        import google.cloud.firestore as gcf  # noqa: PLC0415

        monkeypatch.setattr(
            gcf, "Client", lambda **kw: FakeClient([], updates, **kw)  # type: ignore[arg-type]
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "reconcile_owner.py",
                "--project=sefworkstation-app",
                "--owner-atual=sefworkstation-monitor-homolog",
                "--owner-canonico=ailton-ganem-monitor",
            ],
        )
        exit_code = ro.main()
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "Total: 0 documento(s) encontrado(s)" in out
