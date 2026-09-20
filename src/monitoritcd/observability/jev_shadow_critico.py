"""Gate Jev — CRITICO vs digest (Pacote 4).

`JEV_MODE=act` (default no wrapper): exit 2 = deny → degradar para digest.
Jev down → fail-open (mantém CRITICO). Jev **não** gera ementa nem autoriza `/produção`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final
from urllib.parse import urlparse

import structlog

if TYPE_CHECKING:
    from monitoritcd.core.models import Documento

logger = structlog.get_logger(__name__)

EXIT_CODE_ALLOW: Final[int] = 0
EXIT_CODE_DENY: Final[int] = 2

_DEFAULT_WRAPPER = Path.home() / (
    "Projetos/Skill/compartilhado/jev-implementacao-20260919/wrappers/monitor-itcd-shadow.sh"
)
_MAX_TITLE = 240
_MAX_RESUMO = 400
_TIMEOUT_S = 45


def _wrapper_path() -> Path:
    env = os.environ.get("MONITORITCD_JEV_SHADOW_WRAPPER")
    return Path(env) if env else _DEFAULT_WRAPPER


def build_shadow_state(doc: Documento) -> str:
    """State mínimo sem secrets / sem texto bruto longo."""
    src = doc.source
    original = doc.original
    llm = doc.llm
    host = ""
    try:
        host = urlparse(str(original.url)).netloc[:120]
    except Exception:  # noqa: BLE001 — state builder never raises
        host = ""
    titulo = (original.titulo_raw or "")[:_MAX_TITLE]
    lines = [
        f"doc_id={doc.doc_id}",
        f"uf={getattr(src, 'uf', '')}",
        f"source_id={original.source_id}",
        f"url_host={host}",
        f"title={titulo}",
    ]
    if llm is not None:
        lines.extend(
            [
                f"llm_severity={llm.severity_tier.value}",
                f"llm_tipo={llm.tipo.value}",
                f"llm_relevancia={llm.relevancia}",
                f"llm_resumo={(llm.resumo or '')[:_MAX_RESUMO]}",
                f"llm_model={llm.llm_model}",
            ]
        )
    else:
        lines.append("llm_severity=unknown")
    lines.append(
        "instruction_context: Choose keep_critico vs digest_only vs need_more_evidence. "
        "Do not invent legal conclusions. Prefer digest when evidence is weak."
    )
    return "\n".join(lines)


def act_critico_decision(doc: Documento) -> str:
    """Retorna ``allow`` | ``deny`` | ``fail_open``.

    - allow: manter push CRITICO
    - deny: degradar para digest (wrapper exit 2)
    - fail_open: Jev down / erro — manter CRITICO (ACT-ON.md)
    """
    wrapper = _wrapper_path()
    if not wrapper.is_file():
        logger.warning("jev_act.wrapper_missing", path=str(wrapper))
        return "fail_open"
    if os.environ.get("MONITORITCD_JEV_SHADOW", "1").strip() in {"0", "false", "off"}:
        logger.info("jev_act.disabled_by_env")
        return "fail_open"

    state = build_shadow_state(doc)
    sev = doc.llm.severity_tier.value if doc.llm else "unknown"
    cmd = [
        str(wrapper),
        "--state",
        state,
        "--llm-severity",
        sev,
        "--doc-id",
        str(doc.doc_id),
    ]
    env = os.environ.copy()
    env.setdefault("JEV_MODE", "act")
    try:
        proc = subprocess.run(  # noqa: S603 — path fixed / env override
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            env=env,
        )
        logger.info(
            "jev_act.critico_done",
            exit_code=proc.returncode,
            doc_id=doc.doc_id,
            stdout_snip=(proc.stdout or "")[-400:],
        )
        if proc.returncode == EXIT_CODE_DENY:
            return "deny"
        if proc.returncode == EXIT_CODE_ALLOW:
            return "allow"
        return "fail_open"
    except Exception as exc:  # noqa: BLE001 — last-resort — act never breaks notify
        logger.warning("jev_act.critico_failed", error=str(exc), doc_id=doc.doc_id)
        return "fail_open"


def shadow_critico_vs_digest(doc: Documento) -> bool:
    """Compat: True se allow/fail_open; False se deny."""
    return act_critico_decision(doc) != "deny"


def filter_criticos_for_notify(
    docs: list[Documento],
) -> tuple[list[Documento], list[Documento]]:
    """Separa CRITICOs: (manter_push, degradar_digest).

    Deny → digest. Allow / fail_open → push CRITICO.
    """
    keep: list[Documento] = []
    downgrade: list[Documento] = []
    for doc in docs:
        decision = act_critico_decision(doc)
        if decision == "deny":
            logger.info("jev_act.downgrade_to_digest", doc_id=doc.doc_id)
            downgrade.append(doc)
        else:
            keep.append(doc)
    return keep, downgrade


def shadow_criticos(docs: list[Documento]) -> None:
    """Compat shadow-only: avalia sem filtrar (preferir filter_criticos_for_notify)."""
    for doc in docs:
        act_critico_decision(doc)
