"""Testes do dedup em camadas."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from monitoritcd.core.models import RawItem
from monitoritcd.dedup import (
    _extract_numero_ato,
    _fuzzy_similarity,
    _normalize_for_compare,
    assign_clusters,
    is_duplicate,
)

NOW = datetime.now(UTC)


def _item(
    titulo: str,
    url: str = "https://x.gov.br/p",
    content_hash: str | None = None,
) -> RawItem:
    h = content_hash or ("a" * 60 + "0001")
    return RawItem(
        source_id="x",
        titulo_raw=titulo,
        url=url,
        fetched_at=NOW,
        content_hash=h,
    )


@pytest.mark.unit
class TestExtractNumeroAto:
    def test_extracts_simple_format(self) -> None:
        assert _extract_numero_ato("Lei nº 1234/2026") == "1234/2026"

    def test_extracts_without_prefix(self) -> None:
        assert _extract_numero_ato("Decreto 5678/2026 sobre ITCMD") == "5678/2026"

    def test_extracts_with_dot_separator(self) -> None:
        assert _extract_numero_ato("Lei 999.2026") == "999/2026"

    def test_returns_none_when_no_number(self) -> None:
        assert _extract_numero_ato("Acórdão sobre ITCMD") is None

    def test_extracts_only_first_match(self) -> None:
        # Match retorna o primeiro encontrado
        result = _extract_numero_ato("PL 1234/2026 cita Lei 9999/2025")
        assert result == "1234/2026"


@pytest.mark.unit
class TestNormalize:
    def test_lowers_case(self) -> None:
        assert _normalize_for_compare("ITCMD") == "itcmd"

    def test_collapses_whitespace(self) -> None:
        assert _normalize_for_compare("a  b\t\nc") == "a b c"

    def test_removes_punctuation(self) -> None:
        norm = _normalize_for_compare("Lei nº 1234/2026!")
        assert "!" not in norm
        assert "/" in norm  # / é preservado para dedup numero/ano


@pytest.mark.unit
class TestFuzzySimilarity:
    def test_identical_texts(self) -> None:
        assert _fuzzy_similarity("Lei 1234/2026", "Lei 1234/2026") == 1.0

    def test_similar_texts(self) -> None:
        a = "Lei nº 1234, de 2026"
        b = "Lei 1234/2026"
        assert _fuzzy_similarity(a, b) > 0.5

    def test_unrelated_texts_low_similarity(self) -> None:
        assert _fuzzy_similarity("ITCMD", "futebol") < 0.5


@pytest.mark.unit
class TestAssignClusters:
    def test_empty_input(self) -> None:
        assert assign_clusters([]) == {}

    def test_two_items_with_same_numero_clustered_together(self) -> None:
        i1 = _item("PL nº 1234/2026 — texto A", content_hash="a" * 64)
        i2 = _item(
            "Projeto de Lei 1234/2026 — outro texto",
            url="https://other.gov.br/x",
            content_hash="b" * 64,
        )
        clusters = assign_clusters([i1, i2])
        assert clusters[i1.content_hash] == clusters[i2.content_hash]

    def test_different_numero_different_clusters(self) -> None:
        i1 = _item("PL 1234/2026", content_hash="a" * 64)
        i2 = _item("PL 9999/2026", url="https://b.gov.br/x", content_hash="b" * 64)
        clusters = assign_clusters([i1, i2])
        assert clusters[i1.content_hash] != clusters[i2.content_hash]

    def test_same_hash_same_cluster(self) -> None:
        h = "a" * 64
        i1 = _item("Título A", content_hash=h)
        i2 = _item("Título B", url="https://other.gov.br/", content_hash=h)
        clusters = assign_clusters([i1, i2])
        # Mesmo hash → não reprocessa, mantém único
        assert i1.content_hash in clusters
        assert len(set(clusters.values())) == 1

    def test_fuzzy_clustering(self) -> None:
        # Títulos muito similares sem número de ato
        i1 = _item("Acórdão sobre ITCMD progressivo no Rio", content_hash="a" * 64)
        i2 = _item(
            "Acordao sobre ITCMD progressivo no Rio",
            url="https://other.gov.br/x",
            content_hash="b" * 64,
        )
        clusters = assign_clusters([i1, i2])
        # Diferentes URLs, mas títulos muito similares → mesmo cluster
        assert clusters[i1.content_hash] == clusters[i2.content_hash]

    def test_cluster_id_format(self) -> None:
        i1 = _item("Título", content_hash="a" * 64)
        clusters = assign_clusters([i1])
        cid = clusters[i1.content_hash]
        assert isinstance(cid, str)
        assert len(cid) == 16


@pytest.mark.unit
class TestIsDuplicate:
    def test_duplicate_by_hash(self) -> None:
        item = _item("x", content_hash="x" * 64)
        seen = {"x" * 64}
        assert is_duplicate(item, seen)

    def test_not_duplicate_when_hash_unseen(self) -> None:
        item = _item("x", content_hash="x" * 64)
        assert not is_duplicate(item, set())

    def test_duplicate_by_numero_key(self) -> None:
        item = _item("PL 1234/2026 — texto")
        seen_keys = {"numato:1234/2026"}
        assert is_duplicate(item, set(), seen_keys)
