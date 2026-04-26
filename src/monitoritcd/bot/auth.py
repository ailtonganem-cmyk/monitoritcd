"""Autenticação e rate-limit do bot.

Camadas (ordem de execução):
1. **`verify_chat_id`**: chat_id deve bater com `TELEGRAM_OWNER_CHAT_ID`.
2. **`RateLimiter`**: ≤ 10 comandos/minuto (sliding window).
3. **`TwoStepConfirmation`**: ações destrutivas requerem token efêmero (60s, single-use).

Princípio canônico 1: backend nunca confia.
- Mesmo `chat_id` correto pode ter token Telegram comprometido.
- Rate limit ATIVO mesmo para o dono — defense-in-depth.
- Tokens de confirmação são single-use e expiram (não reutilizáveis).
"""

from __future__ import annotations

import secrets
import time
from collections import deque
from typing import Final

from monitoritcd.core import limits


class BotAuthError(Exception):
    """Erro de autorização no bot."""


class UnauthorizedChatError(BotAuthError):
    """`chat_id` não corresponde ao dono."""


class RateLimitExceededError(BotAuthError):
    """Excedeu limite de comandos por minuto."""


class InvalidConfirmationTokenError(BotAuthError):
    """Token de confirmação inválido, expirado ou já consumido."""


def verify_chat_id(received_chat_id: int, owner_chat_id: int) -> None:
    """Valida que `received_chat_id` é EXATAMENTE igual ao do dono.

    Args:
        received_chat_id: chat_id da mensagem recebida.
        owner_chat_id: TELEGRAM_OWNER_CHAT_ID configurado no env.

    Raises:
        UnauthorizedChatError: se não bate.
    """
    if received_chat_id != owner_chat_id:
        # Mensagem genérica — não revela detalhes ao atacante.
        msg = "chat não autorizado"
        raise UnauthorizedChatError(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter (sliding window)
# ─────────────────────────────────────────────────────────────────────────────

WINDOW_SECONDS: Final[float] = 60.0


class RateLimiter:
    """Sliding window rate limiter por chat_id.

    Mantém os timestamps das últimas requisições. Se exceder
    `BOT_COMMANDS_PER_MINUTE` na janela de 60s, levanta erro.
    """

    def __init__(self, max_per_minute: int = limits.BOT_COMMANDS_PER_MINUTE) -> None:
        self._max = max_per_minute
        self._windows: dict[int, deque[float]] = {}

    def check(self, chat_id: int, *, now: float | None = None) -> None:
        """Levanta `RateLimitExceededError` se excedeu."""
        ts = now if now is not None else time.monotonic()
        window = self._windows.setdefault(chat_id, deque())
        # Remove timestamps fora da janela
        cutoff = ts - WINDOW_SECONDS
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= self._max:
            msg = "rate limit excedido"
            raise RateLimitExceededError(msg)
        window.append(ts)


# ─────────────────────────────────────────────────────────────────────────────
# 2-step confirmation
# ─────────────────────────────────────────────────────────────────────────────


class TwoStepConfirmation:
    """Gerencia tokens de confirmação para operações destrutivas.

    Padrão de uso:
        token = manager.issue("desativar_uf:SP")
        # ... user envia /confirmar <token> ...
        manager.consume(token, "desativar_uf:SP")  # consome ou levanta erro

    Tokens são:
    - Single-use (consumir = remover).
    - TTL configurável (default 60s).
    - Chaveados por ação (proteção contra reuso entre ações).
    """

    def __init__(self, ttl_seconds: int = limits.CONFIRMATION_TOKEN_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._tokens: dict[str, tuple[str, float]] = {}  # token → (action, expires_at)

    def issue(self, action: str, *, now: float | None = None) -> str:
        """Emite novo token para `action`. Retorna a string do token (mostrar ao user)."""
        ts = now if now is not None else time.monotonic()
        # 8 bytes = ~12 chars URL-safe — equilíbrio entre legibilidade e entropia
        token = secrets.token_urlsafe(8)
        self._tokens[token] = (action, ts + self._ttl)
        self._cleanup_expired(ts)
        return token

    def find_action(self, token: str, *, now: float | None = None) -> str | None:
        """Retorna a ação do token sem consumi-lo, ou None se inválido/expirado.

        Útil para handlers determinarem `expected_action` antes de chamar `consume`.
        Não tem efeito colateral.
        """
        ts = now if now is not None else time.monotonic()
        entry = self._tokens.get(token)
        if entry is None:
            return None
        action, expires_at = entry
        if ts > expires_at:
            return None
        return action

    def consume(self, token: str, expected_action: str, *, now: float | None = None) -> None:
        """Consome `token`. Levanta erro se inválido, expirado ou ação errada.

        Estratégia: `_cleanup_expired` no inicio remove tokens vencidos, entao
        qualquer entry remanescente esta valido em tempo. Mismatch de acao nao
        consome (permite o handler tentar varias acoes; `find_action` e mais limpo).
        """
        ts = now if now is not None else time.monotonic()
        self._cleanup_expired(ts)

        entry = self._tokens.get(token)
        if entry is None:
            msg = "token de confirmação inválido"
            raise InvalidConfirmationTokenError(msg)

        action, _expires_at = entry
        if action != expected_action:
            msg = "token de confirmação inválido"
            raise InvalidConfirmationTokenError(msg)
        # Match — pop (consume).
        self._tokens.pop(token, None)

    def _cleanup_expired(self, now: float) -> None:
        """Remove tokens expirados (limpeza periódica)."""
        expired = [t for t, (_, exp) in self._tokens.items() if now > exp]
        for t in expired:
            self._tokens.pop(t, None)
