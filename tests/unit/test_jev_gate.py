"""Testes do gate Jev em modo shadow.

Invariante coberta em todos eles: o gate **nunca** levanta e **nunca** altera o
fluxo do chamador. Falha de helper, timeout, JSON inválido e exceção inesperada
viram `DecisaoJev` com decisão não-allow, sem propagar.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from monitoritcd.llm import jev_gate


@pytest.fixture(autouse=True)
def _limpa_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in (
        "JEV_SHADOW",
        "JEV_SHADOW_MAX_CALLS",
        "JEV_SHADOW_TIMEOUT_SECONDS",
        "JEV_EVAL_SH",
        "JEV_DECIDE_PY",
        "JEV_GATES_DIR",
        "JEV_BACKEND",
    ):
        monkeypatch.delenv(nome, raising=False)
    jev_gate.resetar_orcamento()


def _liga(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_SHADOW", "1")


def _prepara_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    gate_yaml: bool = True,
    helper: bool = True,
    decide: bool = True,
) -> None:
    gates = tmp_path / "gates"
    gates.mkdir(exist_ok=True)
    if gate_yaml:
        (gates / "classificacao.yaml").write_text("ns:\n  supported:\n    type: noul\n")
    monkeypatch.setenv("JEV_GATES_DIR", str(gates))

    sh = tmp_path / "jev-eval.sh"
    py = tmp_path / "decide.py"
    if helper:
        sh.write_text("#!/bin/sh\nexit 0\n")
    if decide:
        py.write_text("print('{}')\n")
    monkeypatch.setenv("JEV_EVAL_SH", str(sh))
    monkeypatch.setenv("JEV_DECIDE_PY", str(py))


@pytest.mark.unit
def test_desligado_por_padrao() -> None:
    """Sem `JEV_SHADOW`, nada sai da máquina."""
    assert jev_gate.habilitado() is False
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.decisao == "desligado"
    assert decisao.motivo == "jev_shadow_off"
    assert decisao.divergente is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("decisao", "bloqueia", "indisponivel"),
    [
        ("deny", True, False),
        ("allow", False, False),
        ("desligado", False, True),
        ("indisponivel", False, True),
        ("erro", False, True),
    ],
)
def test_so_deny_explicito_bloqueia(decisao: str, bloqueia: bool, indisponivel: bool) -> None:
    """Jev indisponível não para a rotina — só um deny recebido bloqueia."""
    resultado = jev_gate.DecisaoJev("citation", decisao, "motivo")
    assert resultado.bloqueia is bloqueia
    assert resultado.indisponivel is indisponivel


@pytest.mark.unit
@pytest.mark.parametrize("valor", ["1", "true", "ON", "sim"])
def test_habilitado_aceita_formas_comuns(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    monkeypatch.setenv("JEV_SHADOW", valor)
    assert jev_gate.habilitado() is True


@pytest.mark.unit
def test_gate_yaml_ausente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch, gate_yaml=False)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.decisao == "indisponivel"
    assert decisao.motivo == "gate_yaml_ausente"


@pytest.mark.unit
def test_helper_ausente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch, helper=False)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.decisao == "indisponivel"
    assert decisao.motivo == "helper_ausente"


@pytest.mark.unit
def test_allow_completo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Caminho feliz: jev-eval grava o JSON, decide devolve allow."""
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch)
    chamadas: list[list[str]] = []

    def _fake(
        argv: list[str], *, timeout: float, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        chamadas.append(argv)
        if argv[0].endswith("jev-eval.sh"):
            saida = Path(argv[argv.index("--out") + 1])
            saida.write_text(json.dumps({"answers": {}}))
            return subprocess.CompletedProcess(argv, 0, "", "")
        payload = {
            "decision": "allow",
            "reason": "default_allow",
            "choice": None,
            "confidence": 0.9,
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    monkeypatch.setattr(jev_gate, "_executar", _fake)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")

    assert decisao.decisao == "allow"
    assert decisao.confianca == pytest.approx(0.9)
    assert decisao.divergente is False
    assert len(chamadas) == 2
    # A chave dos provedores de LLM do MonitorITCD nunca é repassada ao Jev.
    assert "--gate" in chamadas[1]


@pytest.mark.unit
def test_deny_marca_divergencia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Deny em shadow é registrado como divergência — e nada mais acontece."""
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch)

    def _fake(
        argv: list[str], *, timeout: float, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("jev-eval.sh"):
            Path(argv[argv.index("--out") + 1]).write_text("{}")
            return subprocess.CompletedProcess(argv, 0, "", "")
        payload = {
            "decision": "deny",
            "reason": "citation_unsupported:0.2",
            "choice": None,
            "confidence": 0.81,
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    monkeypatch.setattr(jev_gate, "_executar", _fake)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")

    assert decisao.decisao == "deny"
    assert decisao.divergente is True
    assert decisao.motivo.startswith("citation_unsupported")


@pytest.mark.unit
def test_jev_eval_falha_vira_indisponivel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch)

    def _fake(
        argv: list[str], *, timeout: float, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 11, "", "FALLBACK: rede")

    monkeypatch.setattr(jev_gate, "_executar", _fake)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.decisao == "indisponivel"
    assert decisao.motivo == "jev_eval_rc:11"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("excecao", "esperado"),
    [
        (subprocess.TimeoutExpired(cmd="x", timeout=1.0), "timeout_jev_eval"),
        (OSError("sem permissão"), "os_error:OSError"),
    ],
)
def test_falhas_de_processo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    excecao: Exception,
    esperado: str,
) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch)

    def _fake(argv: list[str], *, timeout: float, env: dict[str, str]) -> Any:
        raise excecao

    monkeypatch.setattr(jev_gate, "_executar", _fake)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.decisao == "indisponivel"
    assert decisao.motivo == esperado


@pytest.mark.unit
@pytest.mark.parametrize(
    ("excecao", "esperado"),
    [
        (subprocess.TimeoutExpired(cmd="x", timeout=1.0), "timeout_decide"),
        (OSError("sem permissão"), "os_error:OSError"),
    ],
)
def test_falhas_no_decide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    excecao: Exception,
    esperado: str,
) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch)

    def _fake(argv: list[str], *, timeout: float, env: dict[str, str]) -> Any:
        if argv[0].endswith("jev-eval.sh"):
            Path(argv[argv.index("--out") + 1]).write_text("{}")
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise excecao

    monkeypatch.setattr(jev_gate, "_executar", _fake)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.decisao == "indisponivel"
    assert decisao.motivo == esperado


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stdout", "motivo"),
    [("isto não é json", "decide_json_invalido"), ("[1, 2]", "decide_payload_inesperado")],
)
def test_saida_do_decide_invalida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str, motivo: str
) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch)

    def _fake(
        argv: list[str], *, timeout: float, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("jev-eval.sh"):
            Path(argv[argv.index("--out") + 1]).write_text("{}")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(jev_gate, "_executar", _fake)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.decisao == "erro"
    assert decisao.motivo == motivo


@pytest.mark.unit
def test_confianca_invalida_vira_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch)

    def _fake(
        argv: list[str], *, timeout: float, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        if argv[0].endswith("jev-eval.sh"):
            Path(argv[argv.index("--out") + 1]).write_text("{}")
            return subprocess.CompletedProcess(argv, 0, "", "")
        payload = {"decision": "allow", "reason": "ok", "choice": "proceed", "confidence": "n/a"}
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    monkeypatch.setattr(jev_gate, "_executar", _fake)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.confianca is None
    assert decisao.choice == "proceed"


@pytest.mark.unit
def test_excecao_inesperada_nao_propaga(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch)

    def _explode(*_a: object, **_k: object) -> None:
        msg = "falha interna"
        raise RuntimeError(msg)

    monkeypatch.setattr(jev_gate, "_consultar", _explode)
    decisao = jev_gate.avaliar_sync("citation", "classificacao", "state: x")
    assert decisao.decisao == "erro"
    assert decisao.motivo == "excecao:RuntimeError"


@pytest.mark.unit
def test_orcamento_limita_chamadas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Shadow não pode virar custo: o teto por processo corta o excedente."""
    _liga(monkeypatch)
    monkeypatch.setenv("JEV_SHADOW_MAX_CALLS", "2")
    jev_gate.resetar_orcamento()
    _prepara_stack(tmp_path, monkeypatch, gate_yaml=False)

    motivos = [jev_gate.avaliar_sync("citation", "classificacao", "s").motivo for _ in range(3)]
    assert motivos == ["gate_yaml_ausente", "gate_yaml_ausente", "orcamento_esgotado"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [("", 20), ("5", 5), ("abc", 20), ("-1", 20)],
)
def test_int_env(monkeypatch: pytest.MonkeyPatch, bruto: str, esperado: int) -> None:
    monkeypatch.setenv("JEV_SHADOW_MAX_CALLS", bruto)
    assert jev_gate._int_env("JEV_SHADOW_MAX_CALLS", 20) == esperado


@pytest.mark.unit
@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [("", 8.0), ("2.5", 2.5), ("abc", 8.0), ("0", 8.0)],
)
def test_float_env(monkeypatch: pytest.MonkeyPatch, bruto: str, esperado: float) -> None:
    monkeypatch.setenv("JEV_SHADOW_TIMEOUT_SECONDS", bruto)
    assert jev_gate._float_env("JEV_SHADOW_TIMEOUT_SECONDS", 8.0) == pytest.approx(esperado)


@pytest.mark.unit
def test_montar_state_trunca_e_achata() -> None:
    state = jev_gate.montar_state({"texto": "a" * 5000, "titulo": "linha 1\nlinha 2", "n": 3})
    linhas = state.split("\n")
    assert len(linhas) == 3
    assert linhas[0].endswith("…")
    assert len(linhas[0]) <= jev_gate._LIMITE_CAMPO + len("texto: ") + 1
    assert linhas[1] == "titulo: linha 1 linha 2"
    assert linhas[2] == "n: 3"


@pytest.mark.unit
def test_dir_gates_default_aponta_para_o_repo() -> None:
    """Sem `JEV_GATES_DIR`, o diretório padrão é o do repositório."""
    caminho = jev_gate._dir_gates()
    assert caminho.name == "gates"
    assert caminho.parent.name == "jev"


@pytest.mark.unit
async def test_avaliar_async_desligado() -> None:
    decisao = await jev_gate.avaliar("citation", "classificacao", "state: x")
    assert decisao.decisao == "desligado"


@pytest.mark.unit
async def test_avaliar_async_delega(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _liga(monkeypatch)
    _prepara_stack(tmp_path, monkeypatch, gate_yaml=False)
    decisao = await jev_gate.avaliar("citation", "classificacao", "state: x")
    assert decisao.decisao == "indisponivel"
    assert decisao.gate == "citation"
