"""Cluster temático de documentos (Sugestão #50).

`dedup.assign_clusters` agrupa por similaridade textual.
Esta camada agrupa por **tema + número de ato** entre UFs distintas,
criando alertas consolidados: "Tema X impactado em SP, RJ, MG simultaneamente".

Reduz fadiga de notificação sem perder informação.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monitoritcd.core.models import Documento


@dataclass(frozen=True)
class ThematicCluster:
    """Cluster de documentos sobre o mesmo tema/ato em UFs distintas."""

    cluster_key: str
    topics: tuple[str, ...]
    numero_ato: str | None
    ufs: tuple[str, ...]
    doc_ids: tuple[str, ...]

    @property
    def is_multi_uf(self) -> bool:
        """True se múltiplas UFs estão envolvidas."""
        return len(self.ufs) > 1


def _doc_topics(doc: Documento) -> tuple[str, ...]:
    """Extrai tuple de topics ordenada para chave do cluster."""
    if doc.llm and doc.llm.topics:
        return tuple(sorted(t.value for t in doc.llm.topics))
    return ()


def _doc_numero_ato(doc: Documento) -> str | None:
    """Extrai número de ato dos metadados extraídos pelo LLM."""
    if not doc.llm:
        return None
    return doc.llm.metadados_extraidos.get("numero_ato")


def assign_thematic_clusters(docs: list[Documento]) -> list[ThematicCluster]:
    """Agrupa docs em clusters temáticos.

    Critério: mesmo conjunto de `topics` + mesmo `numero_ato` (se presente)
    → mesmo cluster.

    Returns:
        Lista de clusters; cada cluster pode ter 1+ documento.
    """
    groups: dict[str, list[Documento]] = defaultdict(list)
    for doc in docs:
        topics = _doc_topics(doc)
        if not topics:
            continue  # sem topic não há cluster temático
        numero = _doc_numero_ato(doc)
        # Chave: topics + numero_ato (sem UF)
        key = f"{'+'.join(topics)}|{numero or '_'}"
        groups[key].append(doc)

    clusters: list[ThematicCluster] = []
    for key, group_docs in groups.items():
        ufs_set = sorted({d.source.uf for d in group_docs})
        topics_tuple = _doc_topics(group_docs[0])
        clusters.append(
            ThematicCluster(
                cluster_key=key,
                topics=topics_tuple,
                numero_ato=_doc_numero_ato(group_docs[0]),
                ufs=tuple(ufs_set),
                doc_ids=tuple(sorted(d.doc_id for d in group_docs)),
            )
        )
    return clusters


def multi_uf_clusters(docs: list[Documento]) -> list[ThematicCluster]:
    """Apenas clusters com 2+ UFs (alta prioridade para alerta consolidado)."""
    return [c for c in assign_thematic_clusters(docs) if c.is_multi_uf]
