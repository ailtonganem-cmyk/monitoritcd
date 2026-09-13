"""Testes de `FirestoreStorage` — foco no bug de comparação datetime-vs-string.

Contexto (bug confirmado em produção): `save_documento` grava datetimes via
`model_dump(mode="json")` do pydantic, que serializa como STRING ISO 8601
("...Z"). Porém `list_documentos`/`_search_documentos_by_index` passavam um
objeto `datetime` Python direto para `.where(..., ">=", since)`. No Firestore,
string e timestamp nunca comparam — o filtro sempre retornava vazio,
silenciosamente.

Este módulo cobre:
- `_dt_to_stored`: helper que converte o filtro para o mesmo formato de
  string gravado, incluindo os edge cases de microssegundos e o edge
  lexicográfico ("Z" vs ".") documentado no docstring da função.
- Regressão: `list_documentos` e `search_documentos` (via índice) devem
  enviar STRING (não `datetime`) para `.where("original.fetched_at", ...)`.

`storage/firestore_store.py` é omitido do gate de cobertura (validado via
emulator/integração — ver `pyproject.toml`), mas ganha regressão direta aqui
porque o bug é sutil e não depende de infraestrutura externa para reproduzir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from monitoritcd.storage.firestore_store import (
    COLLECTION_DOCUMENTOS,
    COLLECTION_RUNS,
    FirestoreStorage,
    _dt_to_stored,
    _health_from_stored,
    _stored_to_dt,
)

OWNER = "owner-test"


# ─────────────────────────────────────────────────────────────────────────────
# Fake do client Firestore assíncrono — grava a sequência de chamadas
# ─────────────────────────────────────────────────────────────────────────────


class FakeQuery:
    """Registra `.where`/`.order_by`/`.offset`/`.limit` e simula `.stream()` vazio."""

    def __init__(self, calls: list[tuple[Any, ...]]) -> None:
        self.calls = calls

    def where(self, field: str, op: str, value: Any) -> FakeQuery:
        self.calls.append(("where", field, op, value))
        return self

    def order_by(self, field: str, direction: str | None = None) -> FakeQuery:
        self.calls.append(("order_by", field, direction))
        return self

    def offset(self, n: int) -> FakeQuery:
        self.calls.append(("offset", n))
        return self

    def limit(self, n: int) -> FakeQuery:
        self.calls.append(("limit", n))
        return self

    async def stream(self):  # type: ignore[no-untyped-def]
        return
        yield  # pragma: no cover — torna a função um async generator vazio


class FakeClient:
    """Substitui `google.cloud.firestore.AsyncClient` só para capturar `.where(...)`."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def collection(self, name: str) -> FakeQuery:
        self.calls.append(("collection", name))
        return FakeQuery(self.calls)


def _where_calls(calls: list[tuple[Any, ...]], field: str) -> list[tuple[Any, Any]]:
    return [(c[2], c[3]) for c in calls if c[0] == "where" and c[1] == field]


# ─────────────────────────────────────────────────────────────────────────────
# Fake do client Firestore para `.collection(...).document(...).set(...)`
# ─────────────────────────────────────────────────────────────────────────────


class FakeDocRef:
    """Registra o payload de `.set(...)` para inspeção pelo teste."""

    def __init__(self, collection_name: str, doc_id: str, sink: list[tuple[str, str, Any]]) -> None:
        self._collection_name = collection_name
        self._doc_id = doc_id
        self._sink = sink

    async def set(self, data: dict[str, Any]) -> None:
        self._sink.append((self._collection_name, self._doc_id, data))


class FakeWriteCollection:
    def __init__(self, name: str, sink: list[tuple[str, str, Any]]) -> None:
        self._name = name
        self._sink = sink

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self._name, doc_id, self._sink)


class FakeWriteClient:
    """Substitui `AsyncClient` só para capturar `.collection(...).document(...).set(...)`."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, str, Any]] = []

    def collection(self, name: str) -> FakeWriteCollection:
        return FakeWriteCollection(name, self.writes)


# ─────────────────────────────────────────────────────────────────────────────
# `_dt_to_stored` — helper puro
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestStoredToDtAndHealth:
    def test_roundtrip_dt(self) -> None:
        value = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
        assert _stored_to_dt(_dt_to_stored(value)) == value
        assert _stored_to_dt(None) is None

    def test_health_from_stored(self) -> None:
        now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
        health = _health_from_stored(
            {
                "owner_id": OWNER,
                "source_id": "doe-mg",
                "last_nonzero_at": None,
                "consecutive_zero_runs": 4,
                "last_run_at": _dt_to_stored(now),
                "last_items_count": 0,
            }
        )
        assert health.source_id == "doe-mg"
        assert health.consecutive_zero_runs == 4
        assert health.last_nonzero_at is None
        assert health.last_run_at == now

    def test_health_from_stored_exige_last_run_at(self) -> None:
        with pytest.raises(ValueError, match="last_run_at"):
            _health_from_stored(
                {
                    "owner_id": OWNER,
                    "source_id": "doe-mg",
                    "consecutive_zero_runs": 1,
                    "last_items_count": 0,
                }
            )


@pytest.mark.unit
class TestDtToStored:
    def test_com_microssegundos_preserva_valor(self) -> None:
        value = datetime(2026, 4, 26, 13, 4, 34, 304171, tzinfo=UTC)
        assert _dt_to_stored(value) == "2026-04-26T13:04:34.304171Z"

    def test_sem_microssegundos_emite_seis_digitos_zero(self) -> None:
        """Nunca omite a fração — mesmo quando pydantic omitiria (`microsecond == 0`)."""
        value = datetime(2026, 4, 26, 13, 4, 34, 0, tzinfo=UTC)
        assert _dt_to_stored(value) == "2026-04-26T13:04:34.000000Z"

    def test_naive_assume_utc(self) -> None:
        naive = datetime(2026, 4, 26, 13, 4, 34, 304171)  # noqa: DTZ001 — teste explícito de naive
        aware = datetime(2026, 4, 26, 13, 4, 34, 304171, tzinfo=UTC)
        assert _dt_to_stored(naive) == _dt_to_stored(aware)

    def test_timezone_nao_utc_e_convertido(self) -> None:
        minus3 = timezone(timedelta(hours=-3))
        value = datetime(2026, 4, 26, 10, 4, 34, 304171, tzinfo=minus3)
        assert _dt_to_stored(value) == "2026-04-26T13:04:34.304171Z"

    def test_edge_lexicografico_igualdade_de_segundo(self) -> None:
        """Reproduz o bug de ordenação "Z" (0x5A) > "." (0x2E).

        `since` truncado ao segundo (microsecond=0, típico de `--since
        YYYY-MM-DD`) precisa continuar <= qualquer documento gravado no MESMO
        segundo com microssegundos > 0 — senão o filtro `>=` exclui
        documentos que deveriam entrar.
        """
        since_truncado = datetime(2026, 4, 26, 0, 0, 0, 0, tzinfo=UTC)
        since_stored = _dt_to_stored(since_truncado)

        # Formato que o pydantic REALMENTE grava para um doc no mesmo segundo
        # com microssegundos > 0 (sem a correção deste helper no lado do doc).
        doc_stored_com_micro = "2026-04-26T00:00:00.304171Z"
        # Formato que o pydantic grava quando o doc caiu em microsecond == 0.
        doc_stored_sem_micro = "2026-04-26T00:00:00Z"

        assert since_stored <= doc_stored_com_micro
        assert since_stored <= doc_stored_sem_micro

    def test_edge_lexicografico_sem_correcao_falharia(self) -> None:
        """Prova que o formato ingênuo (sem forçar 6 dígitos) quebra a ordenação.

        Documenta o motivo da escolha de design: formatar `since` truncado
        sem fração ("...00:00:00Z") ficaria lexicograficamente MAIOR que um
        doc no mesmo segundo com microssegundos ("...00:00:00.304171Z"),
        porque "Z" (0x5A) > "." (0x2E) — excluindo incorretamente esse doc.
        """
        since_ingenuo = "2026-04-26T00:00:00Z"
        doc_stored_com_micro = "2026-04-26T00:00:00.304171Z"
        assert since_ingenuo > doc_stored_com_micro  # comportamento incorreto, documentado

    def test_meia_noite_de_data_seca_e_menor_que_qualquer_instante_do_dia(self) -> None:
        since_stored = _dt_to_stored(datetime(2026, 4, 26, 0, 0, 0, tzinfo=UTC))
        mais_tarde = _dt_to_stored(datetime(2026, 4, 26, 23, 59, 59, 999999, tzinfo=UTC))
        assert since_stored <= mais_tarde


# ─────────────────────────────────────────────────────────────────────────────
# Regressão: queries reais devem enviar STRING, não `datetime`
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestListDocumentosQueryUsaString:
    async def test_since_vira_string_no_where(self) -> None:
        client = FakeClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]
        since = datetime(2026, 4, 26, 13, 4, 34, 304171, tzinfo=UTC)

        await storage.list_documentos(since=since)

        matches = _where_calls(client.calls, "original.fetched_at")
        assert matches == [(">=", "2026-04-26T13:04:34.304171Z")]
        assert isinstance(matches[0][1], str)

    async def test_sem_since_nao_adiciona_where_de_data(self) -> None:
        client = FakeClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]

        await storage.list_documentos(since=None)

        assert _where_calls(client.calls, "original.fetched_at") == []

    async def test_collection_correta(self) -> None:
        client = FakeClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]

        await storage.list_documentos(since=datetime(2026, 1, 1, tzinfo=UTC))

        assert ("collection", COLLECTION_DOCUMENTOS) in client.calls


@pytest.mark.unit
class TestSearchDocumentosPorIndiceQueryUsaString:
    async def test_since_vira_string_no_where_via_indice(self) -> None:
        client = FakeClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]
        since = datetime(2026, 4, 26, 0, 0, 0, tzinfo=UTC)

        await storage.search_documentos(terms=["itcd"], since=since)

        matches = _where_calls(client.calls, "original.fetched_at")
        assert matches == [(">=", "2026-04-26T00:00:00.000000Z")]
        assert isinstance(matches[0][1], str)


# ─────────────────────────────────────────────────────────────────────────────
# `save_run_report` — persiste RunReport em monitor_runs
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSaveRunReport:
    async def test_grava_em_monitor_runs_com_run_id_como_doc_id(self) -> None:
        from monitoritcd.orchestrator import RunReport  # noqa: PLC0415

        client = FakeWriteClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]
        report = RunReport(
            run_id="run-abc123",
            started_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
            finished_at=datetime(2026, 4, 26, 12, 5, 0, tzinfo=UTC),
            sources_consulted=3,
            items_stored=7,
        )

        await storage.save_run_report(report)

        assert len(client.writes) == 1
        collection_name, doc_id, data = client.writes[0]
        assert collection_name == COLLECTION_RUNS
        assert doc_id == "run-abc123"
        assert data["run_id"] == "run-abc123"
        assert data["sources_consulted"] == 3
        assert data["items_stored"] == 7
        assert data["duration_seconds"] == 300.0
        assert data["owner_id"] == OWNER
        # started_at/finished_at seguem a convenção `_dt_to_stored` (ISO string
        # com 6 dígitos de microssegundos) — igual a `save_documento` e à query
        # de retenção em `cleanup_retention.py`, garantindo que o filtro casa.
        assert data["started_at"] == "2026-04-26T12:00:00.000000Z"
        assert data["finished_at"] == "2026-04-26T12:05:00.000000Z"

    async def test_owner_id_gravado_e_o_da_instancia_nao_do_report(self) -> None:
        from monitoritcd.orchestrator import RunReport  # noqa: PLC0415

        client = FakeWriteClient()
        storage = FirestoreStorage(client=client, owner_id="dono-especifico")  # type: ignore[arg-type]
        report = RunReport(run_id="run-xyz", started_at=datetime(2026, 4, 26, tzinfo=UTC))

        await storage.save_run_report(report)

        _collection_name, _doc_id, data = client.writes[0]
        assert data["owner_id"] == "dono-especifico"
        # finished_at=None (run não concluído) é preservado como None — não
        # passa pelo `_dt_to_stored`, que não trata None.
        assert data["finished_at"] is None
        assert data["started_at"] == "2026-04-26T00:00:00.000000Z"


@pytest.mark.unit
class TestUpsertSourceRunHealth:
    async def test_grava_em_monitor_source_health(self) -> None:
        from monitoritcd.observability.source_run_health import SourceRunHealth  # noqa: PLC0415
        from monitoritcd.storage.firestore_store import (  # noqa: PLC0415
            COLLECTION_SOURCE_HEALTH,
        )

        client = FakeWriteClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]
        now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
        health = SourceRunHealth(
            owner_id=OWNER,
            source_id="doe-mg",
            last_nonzero_at=None,
            consecutive_zero_runs=7,
            last_run_at=now,
            last_items_count=0,
        )
        await storage.upsert_source_run_health(health)
        assert len(client.writes) == 1
        collection_name, doc_id, data = client.writes[0]
        assert collection_name == COLLECTION_SOURCE_HEALTH
        assert doc_id == "doe-mg"
        assert data["owner_id"] == OWNER
        assert data["source_id"] == "doe-mg"
        assert data["last_nonzero_at"] is None
        assert data["consecutive_zero_runs"] == 7
        assert data["last_run_at"] == "2026-05-19T12:00:00.000000Z"
        assert data["last_items_count"] == 0

    async def test_rejeita_owner_errado(self) -> None:
        from monitoritcd.observability.source_run_health import SourceRunHealth  # noqa: PLC0415
        from monitoritcd.storage.audit_log import OwnershipError  # noqa: PLC0415

        client = FakeWriteClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]
        health = SourceRunHealth(
            owner_id="outro",
            source_id="doe-mg",
            last_run_at=datetime(2026, 5, 19, tzinfo=UTC),
        )
        with pytest.raises(OwnershipError):
            await storage.upsert_source_run_health(health)


class _Snap:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _StoreDoc:
    def __init__(self, store: dict[str, dict[str, dict[str, Any]]], coll: str, doc_id: str) -> None:
        self._store = store
        self._coll = coll
        self._doc_id = doc_id

    async def set(self, data: dict[str, Any]) -> None:
        self._store.setdefault(self._coll, {})[self._doc_id] = data

    async def get(self) -> _Snap:
        return _Snap(self._store.get(self._coll, {}).get(self._doc_id))


class _StoreCollection:
    def __init__(self, store: dict[str, dict[str, dict[str, Any]]], name: str) -> None:
        self._store = store
        self._name = name
        self._filters: list[tuple[str, str, Any]] = []

    def document(self, doc_id: str) -> _StoreDoc:
        return _StoreDoc(self._store, self._name, doc_id)

    def where(self, field: str, op: str, value: Any) -> _StoreCollection:
        self._filters.append((field, op, value))
        return self

    async def stream(self):  # type: ignore[no-untyped-def]
        for data in self._store.get(self._name, {}).values():
            if all(data.get(field) == value for field, op, value in self._filters if op == "=="):
                yield _Snap(data)


class _StoreClient:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> _StoreCollection:
        return _StoreCollection(self.store, name)


@pytest.mark.unit
class TestGetListSourceRunHealth:
    async def test_get_e_list_round_trip(self) -> None:
        from monitoritcd.observability.source_run_health import SourceRunHealth  # noqa: PLC0415

        client = _StoreClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]
        now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
        health = SourceRunHealth(
            owner_id=OWNER,
            source_id="mg_doe",
            last_nonzero_at=now,
            consecutive_zero_runs=2,
            last_run_at=now,
            last_items_count=0,
        )
        await storage.upsert_source_run_health(health)
        got = await storage.get_source_run_health("mg_doe")
        assert got is not None
        assert got.source_id == "mg_doe"
        assert got.consecutive_zero_runs == 2
        assert got.last_nonzero_at == now
        listed = await storage.list_source_run_health()
        assert len(listed) == 1
        assert listed[0].source_id == "mg_doe"

    async def test_get_inexistente(self) -> None:
        client = _StoreClient()
        storage = FirestoreStorage(client=client, owner_id=OWNER)  # type: ignore[arg-type]
        assert await storage.get_source_run_health("missing") is None
