"""Input limits canônicos — Princípio Canônico 2 do CLAUDE.md.

Toda entrada no sistema valida contra estes limites. Excedeu = rejeita.
**Limites são propriedade do backend** — não derivam do que o cliente envia.

Mantenha este módulo como **única fonte da verdade** para limites.
Ao alterar um limite, justifique no commit (impacto + reasoning).
"""

from __future__ import annotations

from typing import Final

# ─────────────────────────────────────────────────────────────────────────────
# String lengths (MAX_LENGTH)
# ─────────────────────────────────────────────────────────────────────────────
MAX_OWNER_ID_LENGTH: Final[int] = 64
MAX_EMAIL_LENGTH: Final[int] = 320  # RFC 5321
MAX_TITLE_LENGTH: Final[int] = 500
MAX_SUMMARY_LENGTH: Final[int] = 2000
MAX_RAW_TEXT_LENGTH: Final[int] = 1_000_000  # 1 MB de texto
MAX_URL_LENGTH: Final[int] = 2048
MAX_BOT_COMMAND_LENGTH: Final[int] = 256
MAX_BOT_ARG_LENGTH: Final[int] = 200
MAX_TAG_LENGTH: Final[int] = 50
MAX_NUMERO_ATO_LENGTH: Final[int] = 30
MAX_ORGAO_EMISSOR_LENGTH: Final[int] = 200
MAX_LLM_MODEL_NAME_LENGTH: Final[int] = 64
MAX_LLM_PROMPT_VERSION_LENGTH: Final[int] = 32
MAX_SOURCE_ID_LENGTH: Final[int] = 128
MAX_SOURCE_NAME_LENGTH: Final[int] = 200
MAX_DOC_ID_LENGTH: Final[int] = 128
MAX_STORAGE_PATH_LENGTH: Final[int] = 512

# ─────────────────────────────────────────────────────────────────────────────
# UF — pattern validado com regex
# ─────────────────────────────────────────────────────────────────────────────
VALID_UFS: Final[tuple[str, ...]] = (
    "AC",
    "AL",
    "AP",
    "AM",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MT",
    "MS",
    "MG",
    "PA",
    "PB",
    "PR",
    "PE",
    "PI",
    "RJ",
    "RN",
    "RS",
    "RO",
    "RR",
    "SC",
    "SP",
    "SE",
    "TO",
)
# Regex que aceita apenas as 27 UFs brasileiras + "_federal".
UF_REGEX: Final[str] = r"^(" + "|".join(VALID_UFS) + r"|_federal)$"
NUMERO_ATO_REGEX: Final[str] = r"^\d{1,5}/\d{4}$"
DURATION_REGEX: Final[str] = r"^\d{1,3}[dwmy]$"  # ex: 7d, 2w, 3m, 1y

# ─────────────────────────────────────────────────────────────────────────────
# List sizes (MAX_ITEMS)
# ─────────────────────────────────────────────────────────────────────────────
MAX_TAGS_PER_DOC: Final[int] = 20
MAX_WATCHES_PER_OWNER: Final[int] = 100
MAX_BATCH_LLM: Final[int] = 10
MAX_KEYWORDS_LIST: Final[int] = 50
MAX_EXTRA_KEYWORDS_TOTAL: Final[int] = 200  # extras dinâmicos via /temas (todos os topics somados)
MIN_EXTRA_KEYWORD_LENGTH: Final[int] = 3
MAX_EXTRA_KEYWORD_LENGTH: Final[int] = 100
MAX_NOTIFICATION_CHANNELS: Final[int] = 5
MAX_ACTIVE_UFS: Final[int] = 27
MAX_METADATA_FIELDS: Final[int] = 30

# ─────────────────────────────────────────────────────────────────────────────
# Object depth (MAX_DEPTH)
# ─────────────────────────────────────────────────────────────────────────────
MAX_JSON_DEPTH: Final[int] = 5
MAX_YAML_DEPTH: Final[int] = 6

# ── Bytes (MAX_BYTES) ────────────────────────────────────────────────────────
MAX_HTML_BYTES: Final[int] = 5 * 1024 * 1024  # 5 MB
MAX_PDF_BYTES: Final[int] = 20 * 1024 * 1024  # 20 MB
MAX_REQUEST_BODY_BYTES: Final[int] = 1 * 1024 * 1024  # 1 MB
MAX_TELEGRAM_MSG_BYTES: Final[int] = 4096  # limite hard do Telegram

# ─────────────────────────────────────────────────────────────────────────────
# Durations (MAX_DURATION) — em segundos
# ─────────────────────────────────────────────────────────────────────────────
HTTP_TIMEOUT_SECONDS: Final[float] = 30.0
LLM_TIMEOUT_SECONDS: Final[float] = 60.0
FUNCTION_TIMEOUT_SECONDS: Final[float] = 540.0  # max GCF gen2
TOTAL_RUN_TIMEOUT_SECONDS: Final[float] = 1800.0  # 30 min

# ─────────────────────────────────────────────────────────────────────────────
# Rate limits & política de polidez
# ─────────────────────────────────────────────────────────────────────────────
BOT_COMMANDS_PER_MINUTE: Final[int] = 10
DOMAIN_REQUESTS_INTERVAL_SECONDS: Final[float] = 2.0
# Groq Free: 30 RPM = 1 req/2s; margem de segurança em 2.5s
LLM_BATCH_DELAY_SECONDS: Final[float] = 2.5
RETRY_MAX_ATTEMPTS: Final[int] = 3
CONFIRMATION_TOKEN_TTL_SECONDS: Final[int] = 60

# ─────────────────────────────────────────────────────────────────────────────
# Severity scoring (relevância → tier)
# ─────────────────────────────────────────────────────────────────────────────
RELEVANCIA_MIN: Final[int] = 0
RELEVANCIA_MAX: Final[int] = 10
RELEVANCIA_THRESHOLD_DESCARTADO: Final[int] = 5  # < 5 vira "descartado"
RELEVANCIA_THRESHOLD_BAIXA: Final[int] = 5  # 5-6 = baixa
RELEVANCIA_THRESHOLD_NORMAL: Final[int] = 7  # 7-8 = normal
RELEVANCIA_THRESHOLD_ALTA: Final[int] = 8  # >=9 alta. >=9.5 critico (semantico).
RELEVANCIA_THRESHOLD_CRITICO: Final[int] = 9
