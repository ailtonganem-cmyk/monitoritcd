# Threat Model (STRIDE) — MonitorITCD

> Sugestão #41 — modelagem formal de ameaças com framework STRIDE.
> Complementa `SECURITY.md` com taxonomia explícita.

## Sistema em escopo

Pipeline single-user de monitoramento de atos legislativos brasileiros.
Componentes:
1. GitHub Actions runner (cron diário).
2. Cloud Functions (proxy_br, bot_webhook, canary_filter).
3. Firestore (metadados) + Firebase Storage (HTML/PDF brutos).
4. Telegram Bot API.
5. SMTP Gmail.
6. LLM externa (Gemini/Groq).

## Ameaças por categoria STRIDE

### S — Spoofing (falsificação de identidade)

| Ameaça | Mitigação |
|---|---|
| Bot Telegram falso enviando comandos | Validação `chat_id == TELEGRAM_OWNER_CHAT_ID` em `bot/auth.py:40` |
| Webhook Telegram com payload spoofed | `X-Telegram-Bot-Api-Secret-Token` verificado em `functions/bot_webhook` |
| Service account vazada usada de outro projeto | `assert_owner` em todas as mutations Firestore |
| Cloud Function `proxy_br` chamada por terceiro | `X-Proxy-Token` (32+ bytes) verificado |

### T — Tampering (modificação não autorizada)

| Ameaça | Mitigação |
|---|---|
| Modificação de `original.*` por LLM | Pydantic `frozen=True` em `RawItem`; CLAUDE.md §5 |
| Tampering em audit log | Hash chain com `prev_hash`; `audit.verify_chain()` em runtime (Sugestão #25) |
| Modificação de YAMLs em PR malicioso | Pre-commit + CI: `lint_sources_yaml.py`, `gitleaks`, `detect-secrets` |
| Race condition em writes Firestore | Single-user; sem concorrência. Mas idempotência via `content_hash` |

### R — Repudiation (negação de ação)

| Ameaça | Mitigação |
|---|---|
| Dono nega ter ativado UF X | `audit_log` com timestamp + hash chain |
| Sistema nega ter notificado item Y | `documento.notificacao.enviada_em` persistente |
| Disputa sobre versão do prompt LLM | `LLMResult.llm_prompt_version` + `PROMPT_VERSION` snapshot test (Sugestão #13) |

### I — Information Disclosure (vazamento)

| Ameaça | Mitigação |
|---|---|
| Token Telegram em log | `structlog` redactor processor (`security/log_redactor.py`) |
| Service account JSON em disco | Lido só do env var; em CI, escrito em `$RUNNER_TEMP` chmod 600 |
| API key em commit | Pre-commit: `gitleaks`, `detect-secrets`, `check_secret_literals.py` |
| Dados Firestore lidos por terceiro | `firestore.rules` deny all + App Check |
| Conteúdo coletado público interpretado como sensível | N/A — fontes já são públicas (atos legislativos publicados) |

### D — Denial of Service

| Ameaça | Mitigação |
|---|---|
| Fonte lenta trava cron | `httpx.Timeout(30s)` + `asyncio.gather` isola por fonte |
| Bot floodado por mensagens | Rate limit global (10/min) + por comando (Sugestão #24) |
| Quota LLM esgotada | Fallback Gemini→Groq + DLQ (Sugestão #31) |
| Grande payload em comando bot | `MAX_LENGTH` em pydantic (Princípio canônico 2) |
| YAML bomb em fonte | `_check_yaml_depth` em `source_loader.py:30` |

### E — Elevation of Privilege

| Ameaça | Mitigação |
|---|---|
| SSRF: URL aponta para metadata.google.internal | `validate_url` rejeita IP literal privado, blocklist explícita |
| Prompt injection vira execução de código | LLM produz só JSON; pydantic `extra="forbid"` |
| Path traversal em `raw_storage_path` | `pathlib.PurePosixPath`; reject `..` e absoluto |
| Markdown injection no Telegram | Escape MarkdownV2 antes de envio (`security/markdown_escape.py`) |
| XSS em email | Jinja2 `autoescape=True` |
| Shell injection | Não há `shell=True`; `subprocess` sempre `list[str]` |

## Threat actors

- **Script kiddie scanner**: ataca surface pública (webhook bot). Mitigado por `chat_id` validação.
- **Operador comprometido**: dono com 2FA quebrado. Audit log + rate limit por comando reduzem blast radius.
- **Dependência maliciosa** (typosquat ou supply chain): `pip-audit` + `pre-commit detect-secrets` + lockfile.

## Threat actors fora de escopo

- Estado-nação com 0day: não temos como mitigar; mas dados são públicos.
- Atacante físico ao laptop do dono: fora do TM.

## Revisão

Este documento deve ser revisado a cada mudança arquitetural significativa
(novo canal, novo storage, expansão multi-user, etc.).

## Referências

- `SECURITY.md` — políticas operacionais
- `CLAUDE.md` Seção 7 — princípios canônicos e padrões
- ADRs em `docs/adr/`
