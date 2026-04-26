"""Bot Telegram interativo — comandos do dono.

Princípios canônicos aplicados:
1. **`chat_id` validation** — apenas o dono envia comandos.
2. **Rate limit** — 10 comandos/minuto, mesmo para o dono.
3. **Confirmação 2 passos** — operações destrutivas exigem token efêmero.
4. **input_limits** — todo argumento validado por pydantic.
"""

from __future__ import annotations

from monitoritcd.bot.auth import (
    BotAuthError,
    RateLimiter,
    TwoStepConfirmation,
    UnauthorizedChatError,
    verify_chat_id,
)
from monitoritcd.bot.handlers import (
    BotContext,
    HandlerResult,
    parse_command,
)

__all__ = [
    "BotAuthError",
    "BotContext",
    "HandlerResult",
    "RateLimiter",
    "TwoStepConfirmation",
    "UnauthorizedChatError",
    "parse_command",
    "verify_chat_id",
]
