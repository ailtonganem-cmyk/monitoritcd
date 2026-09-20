"""Gate Jev (TypeSafe) em modo shadow — observa, não decide.

Fase 0 do plano em `docs/JEV-IA-INVENTARIO.md`. O objetivo aqui é medir quanto
o Jev discordaria da pipeline **antes** de qualquer deny valer. Nada neste
módulo altera o fluxo do MonitorITCD:

- `avaliar` sempre devolve uma `DecisaoJev` e **nunca** propaga exceção;
- o chamador loga o resultado e segue o caminho que já seguia;
- desligado por padrão. Só roda com `JEV_SHADOW=1` no ambiente.

**Indisponibilidade do Jev não para o trabalho** (decisão do founder,
2026-09-20). Jev fora do ar, sem chave, com timeout ou com erro de parse não
interrompe, não adia e não degrada a rotina: a pipeline segue exatamente como
seguiria sem Jev nenhum. Isso vale para a Fase 0 e para todas as fases
seguintes — ver `DecisaoJev.bloqueia`, que só é verdadeiro num `deny` explícito
e efetivamente recebido.

Contrato da frota (`~/Projetos/Skill/compartilhado/jev.md`):

1. Perguntas tipadas em inglês; prosa em pt-BR.
2. Jev não escreve conteúdo de produto — arbitra forks tipados.
3. Jev indisponível → fail-open. Aqui o fail-open é total: shadow não bloqueia.
4. `yolo_by_jev` nunca vira `True`; este módulo não lê nem repassa esse campo
   como autorização de nada.

Egress: o `state` enviado carrega trecho do texto coletado (conteúdo público,
com proveniência) e a saída do classificador. Nunca carrega chave de API,
credencial ou configuração de provedor. O truncamento em `_LIMITE_CAMPO`
limita o que sai da máquina.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import structlog

logger = structlog.get_logger(__name__)

# Caminhos canônicos do stack Jev. Todos sobrescrevíveis por ambiente para que
# CI e HML não dependam do layout de um computador específico.
_HELPER_PADRAO: Final[str] = "~/Projetos/Skill/tools/jev-eval/jev-eval.sh"
_DECIDE_PADRAO: Final[str] = (
    "~/Projetos/Skill/compartilhado/jev-implementacao-20260919/lib/jev-act-decide.py"
)

# Teto de caracteres por campo do state. Corta texto coletado longo antes do
# egress e mantém o payload previsível.
_LIMITE_CAMPO: Final[int] = 1200

# Defaults conservadores: shadow não pode atrasar a pipeline nem gastar cota.
_TIMEOUT_PADRAO: Final[float] = 8.0
_MAX_CHAMADAS_PADRAO: Final[int] = 20


@dataclass(frozen=True)
class DecisaoJev:
    """Resultado de uma consulta shadow. `decisao` nunca é aplicada nesta fase."""

    gate: str
    decisao: str
    """`allow`, `deny`, `desligado`, `indisponivel` ou `erro`."""
    motivo: str
    choice: str | None = None
    confianca: float | None = None
    duracao_ms: int = 0

    @property
    def divergente(self) -> bool:
        """True quando o Jev negaria o caminho que a pipeline vai seguir mesmo assim."""
        return self.decisao == "deny"

    @property
    def indisponivel(self) -> bool:
        """True quando não houve veredito: Jev fora do ar, desligado ou com erro."""
        return self.decisao in {"desligado", "indisponivel", "erro"}

    @property
    def bloqueia(self) -> bool:
        """Única forma legítima de o Jev barrar algo — e só a partir da Fase 1.

        Decisão do founder (2026-09-20): **Jev indisponível não interrompe a
        rotina.** Sem veredito, o trabalho segue como se o Jev não existisse.
        Por isso só um `deny` explícito e recebido bloqueia; `desligado`,
        `indisponivel` e `erro` são todos fail-open.

        Exceção única, herdada do contrato da frota: o gate de produção nunca é
        autorizado por ausência de resposta. Lá, ausência de veredito significa
        seguir sem liberar produção — nunca liberar.
        """
        return self.decisao == "deny"


def _int_env(nome: str, padrao: int) -> int:
    bruto = (os.environ.get(nome) or "").strip()
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        return padrao
    return valor if valor >= 0 else padrao


def _float_env(nome: str, padrao: float) -> float:
    bruto = (os.environ.get(nome) or "").strip()
    if not bruto:
        return padrao
    try:
        valor = float(bruto)
    except ValueError:
        return padrao
    return valor if valor > 0 else padrao


@dataclass
class _Orcamento:
    """Teto de chamadas por processo — shadow não pode virar custo de produção."""

    usadas: int = 0
    teto: int = field(
        default_factory=lambda: _int_env("JEV_SHADOW_MAX_CALLS", _MAX_CHAMADAS_PADRAO),
    )

    def consumir(self) -> bool:
        if self.usadas >= self.teto:
            return False
        self.usadas += 1
        return True


_orcamento = _Orcamento()


def habilitado() -> bool:
    """Shadow é opt-in. Sem `JEV_SHADOW` verdadeiro, nada sai da máquina."""
    return (os.environ.get("JEV_SHADOW") or "").strip().lower() in {"1", "true", "on", "sim"}


def resetar_orcamento() -> None:
    """Zera o contador de chamadas. Usado entre execuções e em teste."""
    global _orcamento  # noqa: PLW0603 - contador de processo, intencional
    _orcamento = _Orcamento()


def _caminho(env: str, padrao: str) -> Path:
    bruto = (os.environ.get(env) or "").strip() or padrao
    return Path(bruto).expanduser()


def _dir_gates() -> Path:
    bruto = (os.environ.get("JEV_GATES_DIR") or "").strip()
    if bruto:
        return Path(bruto).expanduser()
    return Path(__file__).resolve().parents[3] / "docs" / "jev" / "gates"


def _texto(valor: object, *, limite: int = _LIMITE_CAMPO) -> str:
    """Normaliza um campo do state: string de uma linha, truncada."""
    texto = " ".join(str(valor or "").split())
    if len(texto) > limite:
        return texto[:limite] + "…"
    return texto


def montar_state(campos: dict[str, Any]) -> str:
    """Serializa o state em `chave: valor` por linha, cada valor truncado.

    Formato em texto (não JSON) porque o Jev recebe o state como prosa factual.
    Chaves em inglês ficam a cargo do chamador; o contrato de perguntas é EN.
    """
    linhas = [f"{chave}: {_texto(valor)}" for chave, valor in campos.items()]
    return "\n".join(linhas)


def _executar(
    argv: list[str], *, timeout: float, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv fixo, sem shell, binário da frota
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def _consultar(gate: str, stem: str, state: str, timeout: float) -> DecisaoJev:  # noqa: PLR0911
    """Chama `jev-eval.sh` e `jev-act-decide.py`. Toda falha vira `indisponivel`."""
    inicio = time.monotonic()

    def _fim() -> int:
        return int((time.monotonic() - inicio) * 1000)

    perguntas = _dir_gates() / f"{stem}.yaml"
    if not perguntas.is_file():
        return DecisaoJev(gate, "indisponivel", "gate_yaml_ausente", duracao_ms=_fim())

    helper = _caminho("JEV_EVAL_SH", _HELPER_PADRAO)
    decide = _caminho("JEV_DECIDE_PY", _DECIDE_PADRAO)
    if not helper.is_file() or not decide.is_file():
        return DecisaoJev(gate, "indisponivel", "helper_ausente", duracao_ms=_fim())

    # Env enxuto: o helper resolve a chave do Jev sozinho (arquivo ou
    # TYPESAFE_API_KEY já exportada). Nenhuma chave de LLM do MonitorITCD é
    # repassada — o Jev não precisa delas e não deve vê-las.
    env = {
        chave: valor
        for chave, valor in os.environ.items()
        if chave in {"HOME", "PATH", "LANG", "TYPESAFE_API_KEY", "JEV_BACKEND", "JEV_SESSION_TIER"}
    }

    with tempfile.TemporaryDirectory(prefix="jev-shadow-") as tmp:
        saida = Path(tmp) / "jev.json"
        try:
            proc = _executar(
                [
                    str(helper),
                    "--backend",
                    env.get("JEV_BACKEND") or "auto",
                    "--questions",
                    str(perguntas),
                    "--state",
                    state,
                    "--out",
                    str(saida),
                ],
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return DecisaoJev(gate, "indisponivel", "timeout_jev_eval", duracao_ms=_fim())
        except OSError as e:
            return DecisaoJev(
                gate, "indisponivel", f"os_error:{type(e).__name__}", duracao_ms=_fim()
            )

        if proc.returncode != 0 or not saida.is_file():
            return DecisaoJev(
                gate, "indisponivel", f"jev_eval_rc:{proc.returncode}", duracao_ms=_fim()
            )

        try:
            veredito = _executar(
                ["python3", str(decide), "--jev-json", str(saida), "--gate", gate],
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return DecisaoJev(gate, "indisponivel", "timeout_decide", duracao_ms=_fim())
        except OSError as e:
            return DecisaoJev(
                gate, "indisponivel", f"os_error:{type(e).__name__}", duracao_ms=_fim()
            )

    try:
        payload = json.loads(veredito.stdout or "{}")
    except json.JSONDecodeError:
        return DecisaoJev(gate, "erro", "decide_json_invalido", duracao_ms=_fim())
    if not isinstance(payload, dict):
        return DecisaoJev(gate, "erro", "decide_payload_inesperado", duracao_ms=_fim())

    confianca = payload.get("confidence")
    try:
        confianca = float(confianca) if confianca is not None else None
    except (TypeError, ValueError):
        confianca = None

    return DecisaoJev(
        gate=gate,
        decisao=str(payload.get("decision") or "erro"),
        motivo=str(payload.get("reason") or ""),
        choice=str(payload["choice"]) if payload.get("choice") is not None else None,
        confianca=confianca,
        duracao_ms=_fim(),
    )


def avaliar_sync(
    gate: str, stem: str, state: str, *, contexto: dict[str, Any] | None = None
) -> DecisaoJev:
    """Consulta shadow síncrona. Nunca levanta; nunca altera o fluxo do chamador."""
    if not habilitado():
        return DecisaoJev(gate, "desligado", "jev_shadow_off")
    if not _orcamento.consumir():
        return DecisaoJev(gate, "desligado", "orcamento_esgotado")

    timeout = _float_env("JEV_SHADOW_TIMEOUT_SECONDS", _TIMEOUT_PADRAO)
    try:
        decisao = _consultar(gate, stem, state, timeout)
    except Exception as e:  # noqa: BLE001 - shadow jamais derruba a pipeline
        decisao = DecisaoJev(gate, "erro", f"excecao:{type(e).__name__}")

    logger.info(
        "jev.shadow",
        gate=decisao.gate,
        decisao=decisao.decisao,
        motivo=decisao.motivo,
        choice=decisao.choice,
        confianca=decisao.confianca,
        duracao_ms=decisao.duracao_ms,
        divergente=decisao.divergente,
        **(contexto or {}),
    )
    return decisao


async def avaliar(
    gate: str, stem: str, state: str, *, contexto: dict[str, Any] | None = None
) -> DecisaoJev:
    """Versão async — roda a consulta em thread para não bloquear o loop."""
    if not habilitado():
        return DecisaoJev(gate, "desligado", "jev_shadow_off")
    return await asyncio.to_thread(avaliar_sync, gate, stem, state, contexto=contexto)
