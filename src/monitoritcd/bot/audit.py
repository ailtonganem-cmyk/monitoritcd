"""Helper para registrar ações do bot no audit log.

CLAUDE.md §7 exige que toda ação do bot grave em `audit_log/` com
`actor`, `action`, `payload`, `result`. Este módulo encapsula a lógica
para que cada handler chame `log_bot_action(...)` em uma linha.

Princípios canônicos:
- Falha do audit **não** derruba handler (CLAUDE.md §10: "Falha em uma fonte
  não pode derrubar a execução"). Logado como warning.
- Hash chain mantida via `storage.get_last_audit_hash()` + `payload_hash`
  do payload normalizado.
- Payload sanitizado antes do hash (ordem estável, sem PII conhecida).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from monitoritcd.core.models import AuditLogEntry

if TYPE_CHECKING:
    from monitoritcd.bot.handlers import BotContext

logger = structlog.get_logger(__name__)

# Origem do actor para mutações via bot Telegram
BOT_ACTOR = "bot:OWNER"


def _hash_payload(payload: dict[str, Any]) -> str:
    """SHA-256 hex do payload em JSON canônico (sort_keys, ensure_ascii=False)."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def log_bot_action(
    ctx: BotContext,
    *,
    action: str,
    payload: dict[str, Any],
    result: str = "success",
    error: str | None = None,
) -> None:
    """Persiste 1 entry no audit log para uma ação do bot.

    Args:
        ctx: BotContext com storage + settings.
        action: rótulo curto (ex: "bot.marcar", "bot.observar.add").
        payload: dict descrevendo a ação (sem secrets nem PII bruta).
        result: "success" | "failure".
        error: mensagem de erro sanitizada (apenas se failure).

    Falhas internas (storage offline, hash chain quebrada) são logadas
    como warning e descartadas — não propagam para o handler.
    """
    try:
        prev_hash = await ctx.storage.get_last_audit_hash()
        entry = AuditLogEntry(
            owner_id=ctx.settings.OWNER_ID,
            entry_id=uuid4().hex,
            timestamp=datetime.now(UTC),
            actor=BOT_ACTOR,
            action=action,
            payload_hash=_hash_payload(payload),
            prev_hash=prev_hash,
            result=result,  # type: ignore[arg-type]
            error=error,
        )
        await ctx.storage.append_audit(entry)
    except Exception as e:  # noqa: BLE001 — audit é last-resort: nunca derruba handler
        logger.warning("bot.audit.failed", action=action, error=str(e))
