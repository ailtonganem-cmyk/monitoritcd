"""Configura bot Telegram via Bot API (#143, #144).

Uso:
    TELEGRAM_BOT_TOKEN=... python scripts/setup_bot_commands.py

Aplica:
- setMyCommands — lista de comandos visível no menu (/) do Telegram (#143)
- setMyDescription — descrição PT-BR exibida ao abrir o bot (#144)
- setMyShortDescription — bio curta

Princípios canônicos aplicados:
- Princípio 3: token nunca hardcoded; via env var TELEGRAM_BOT_TOKEN
- Princípio 1: validação básica de status code antes de prosseguir
"""

from __future__ import annotations

import os
import sys
from typing import Final

import httpx

TELEGRAM_API_BASE: Final[str] = "https://api.telegram.org"

# Lista de comandos visíveis no menu (/) — alinhada com bot/handlers.py
COMMANDS: Final[list[dict[str, str]]] = [
    {"command": "start", "description": "Saudação e lista de comandos"},
    {"command": "help", "description": "Ajuda contextual"},
    {"command": "status", "description": "Última coleta, fontes, cota LLM"},
    {"command": "buscar", "description": "Buscar em documentos coletados"},
    {"command": "observar", "description": "Watch list — alerta em match"},
    {"command": "marcar", "description": "Tag pessoal em documento"},
    {"command": "favoritos", "description": "Listar favoritos"},
    {"command": "silenciar", "description": "Mute UF/tipo por período"},
    {"command": "estados", "description": "Listar/ativar/desativar UFs"},
    {"command": "fontes", "description": "Status das fontes"},
    {"command": "relatorio", "description": "Digest sob demanda"},
    {"command": "reprocessar", "description": "Reclassificar período"},
    {"command": "quota", "description": "Uso de cotas (LLM, Firestore, Storage)"},
]

DESCRIPTION: Final[str] = (
    "Sistema autônomo de monitoramento de mudanças legislativas, normativas e "
    "jurisprudenciais sobre ITCD/ITCMD/ITD, sucessões e regime de bens nos 27 "
    "entes federativos brasileiros. Uso pessoal restrito ao dono."
)

SHORT_DESCRIPTION: Final[str] = "Monitor ITCD/sucessões/regime de bens — uso pessoal."


def _post(token: str, method: str, payload: dict[str, object]) -> dict[str, object]:
    """Chama Bot API; falha loudly em erros."""
    url = f"{TELEGRAM_API_BASE}/bot{token}/{method}"
    response = httpx.post(url, json=payload, timeout=15.0)
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        msg = f"{method} falhou: {body!r}"
        raise RuntimeError(msg)
    return body  # type: ignore[no-any-return]


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.stderr.write("ERRO: TELEGRAM_BOT_TOKEN não configurado.\n")
        return 1

    print("→ setMyCommands")
    _post(token, "setMyCommands", {"commands": COMMANDS, "language_code": "pt"})

    print("→ setMyDescription")
    _post(token, "setMyDescription", {"description": DESCRIPTION, "language_code": "pt"})

    print("→ setMyShortDescription")
    _post(
        token,
        "setMyShortDescription",
        {"short_description": SHORT_DESCRIPTION, "language_code": "pt"},
    )

    print("✓ Bot configurado. Verifique no Telegram com `/start`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
