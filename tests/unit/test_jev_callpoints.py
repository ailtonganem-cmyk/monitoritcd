"""Callpoints shadow do Jev — garantem que observar não muda o fluxo.

O que estes testes protegem: com o shadow ligado e o Jev respondendo `deny`,
a pipeline precisa produzir exatamente o mesmo resultado que produz com o
shadow desligado. Fase 0 observa; não decide.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from monitoritcd.core.models import (
    LLMResult,
    Parser,
    RawItem,
    SeverityTier,
    Source,
    TipoAto,
    TipoFonte,
)
from monitoritcd.llm import jev_gate
from monitoritcd.orchestrator import _jev_shadow_classificacao
from monitoritcd.painel import ia_provedores

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _limpa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEV_SHADOW", raising=False)
    jev_gate.resetar_orcamento()


def _source() -> Source:
    return Source(
        id="fonte-teste",
        nome="Fonte de Teste",
        uf="MG",
        tipo=TipoFonte.SEFAZ,
        url="https://exemplo.gov.br/atos",
        parser=Parser.GENERIC_HTML,
    )


def _item() -> RawItem:
    return RawItem(
        source_id="fonte-teste",
        titulo_raw="Resolução 123/2026 altera alíquota do ITCD",
        url="https://exemplo.gov.br/atos/123",
        texto_raw="A Resolução 123/2026 altera a alíquota do ITCD em Minas Gerais.",
        data_publicacao=datetime(2026, 9, 1, tzinfo=UTC),
        fetched_at=datetime(2026, 9, 2, tzinfo=UTC),
        content_hash="a" * 64,
    )


def _llm_result(tier: SeverityTier) -> LLMResult:
    return LLMResult(
        classified_at=datetime(2026, 9, 2, tzinfo=UTC),
        llm_model="gemini-2.5-flash",
        llm_prompt_version="v2.1",
        tipo=TipoAto.INSTRUCAO_NORMATIVA,
        relevancia=9,
        severity_tier=tier,
        resumo="Resolução altera alíquota do ITCD.",
        resumo_completo="A Resolução 123/2026 altera a alíquota do ITCD em Minas Gerais.",
        pontos_chave=["Altera alíquota"],
        motivo_relevancia="Mudança de alíquota.",
        contexto="",
        assuntos_relacionados=[],
        metadados_extraidos={"numero_ato": "123/2026", "orgao_emissor": "SEFAZ-MG"},
        tags=["itcd"],
        topics=["itcd"],
    )


def _registrar_chamadas(monkeypatch: pytest.MonkeyPatch, decisao: str) -> list[tuple[str, str]]:
    """Substitui a consulta real e devolve a lista de `(gate, stem)` chamados."""
    chamadas: list[tuple[str, str]] = []

    def _fake(gate: str, stem: str, state: str, timeout: float) -> jev_gate.DecisaoJev:
        chamadas.append((gate, stem))
        assert state, "state não pode ir vazio ao Jev"
        return jev_gate.DecisaoJev(gate, decisao, "teste")

    monkeypatch.setenv("JEV_SHADOW", "1")
    monkeypatch.setattr(jev_gate, "_consultar", _fake)
    return chamadas


@pytest.mark.unit
async def test_classificacao_consulta_citation(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = _registrar_chamadas(monkeypatch, "allow")
    await _jev_shadow_classificacao(_source(), _item(), _llm_result(SeverityTier.NORMAL))
    assert chamadas == [("citation", "classificacao")]


@pytest.mark.unit
async def test_critico_consulta_os_dois_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = _registrar_chamadas(monkeypatch, "allow")
    await _jev_shadow_classificacao(_source(), _item(), _llm_result(SeverityTier.CRITICO))
    assert chamadas == [("citation", "classificacao"), ("critico", "critico")]


@pytest.mark.unit
async def test_deny_nao_interrompe_o_fluxo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deny em shadow é só log: a função retorna normalmente."""
    chamadas = _registrar_chamadas(monkeypatch, "deny")
    await _jev_shadow_classificacao(_source(), _item(), _llm_result(SeverityTier.CRITICO))
    assert len(chamadas) == 2


@pytest.mark.unit
async def test_shadow_desligado_nao_consulta(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[str] = []

    def _fake(*_a: object, **_k: object) -> None:
        chamadas.append("chamou")

    monkeypatch.setattr(jev_gate, "_consultar", _fake)
    await _jev_shadow_classificacao(_source(), _item(), _llm_result(SeverityTier.CRITICO))
    assert chamadas == []


@pytest.mark.unit
def test_painel_grava_cadeia_com_shadow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Gravar a cadeia consulta o Jev e persiste igual, mesmo com deny."""
    chamadas = _registrar_chamadas(monkeypatch, "deny")
    monkeypatch.setattr(ia_provedores, "usar_firestore", lambda: False, raising=False)

    itens: list[dict[str, Any]] = [
        {"id": "gemini", "familia": "google", "habilitado": True, "modelo": "gemini-2.5-flash"},
    ]
    resultado = ia_provedores.gravar(tmp_path, itens)

    assert chamadas == [("material", "cadeia-painel")]
    assert [i["familia"] for i in resultado] == ["google"]


@pytest.mark.unit
def test_resumo_cadeia_nao_expoe_chave() -> None:
    resumo = ia_provedores._resumo_cadeia(
        [
            {"familia": "google", "modelo": "gemini-2.5-flash", "esforco": "medio"},
            {
                "familia": "groq",
                "modelo": "llama-3.3-70b-versatile",
                "esforco": "baixo",
                "habilitado": False,
            },
        ],
    )
    assert resumo == "google/gemini-2.5-flash@medio → groq/llama-3.3-70b-versatile@baixo (off)"
    assert "key" not in resumo.lower()


@pytest.mark.unit
def test_resumo_cadeia_vazia() -> None:
    assert ia_provedores._resumo_cadeia([]) == "empty"
