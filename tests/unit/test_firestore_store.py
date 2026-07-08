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
    FirestoreStorage,
    _dt_to_stored,
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
# `_dt_to_stored` — helper puro
# ─────────────────────────────────────────────────────────────────────────────


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
