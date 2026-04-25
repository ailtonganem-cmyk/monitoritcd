# SECURITY.md — Threat Model

## Princípios canônicos (do CLAUDE.md)

1. 🔒 **Backend nunca confia no frontend** — incluindo bot Telegram do dono.
2. 📏 **`input_limits` obrigatórios** — todo input rejeitado se exceder limite.
3. 🔐 **Secrets PROIBIDOS em código fonte** — sem exceção.

## Modelo de confiança

| Componente | Trust | Notas |
|---|---|---|
| Service account Firebase | Alto | Único caminho de escrita; chave rotacionável |
| GitHub Actions runner | Médio | US-based, isolado por job |
| Bot Telegram (chat_id do dono) | **Não confiado por default** | Token pode ser comprometido |
| Webhooks externos | Não confiados | Validação de assinatura obrigatória |
| Conteúdo coletado (HTML/PDF) | Hostil | Sanitizado em `core/sanitize.py` |
| YAMLs de fonte | Médio | URL validada anti-SSRF na carga |
| Audit log | Imutável | Append-only com hash chain |

## Ameaças & mitigações

### T1: Service Account vazada
**Impacto**: leitura/escrita de qualquer dado Firestore.
**Mitigações**:
- `owner_id` assertion em todas as mutations (defense-in-depth: limita blast).
- Firestore Rules `deny all` → apenas SA do projeto acessa.
- App Check enforce em Storage e Firestore.
- Detecção via gitleaks/detect-secrets em pre-commit + CI.
- Rotação 90 dias (lembrete via Telegram).

### T2: Bot Telegram comprometido
**Impacto**: comandos não-autorizados ao sistema.
**Mitigações**:
- `verify_chat_id` rejeita qualquer chat ≠ TELEGRAM_OWNER_CHAT_ID.
- Rate limit 10/min mesmo para o dono.
- Operações destrutivas requerem token efêmero (60s, single-use).
- Validação de webhook: `X-Telegram-Bot-Api-Secret-Token`.

### T3: SSRF via YAML de fonte
**Impacto**: requests internos contornando firewall.
**Mitigações**:
- `validate_url` em `security/url_validator.py`:
  - Apenas `https://`.
  - Bloqueio RFC1918, link-local, multicast, loopback.
  - Bloqueio de cloud metadata endpoints (AWS/GCP/Azure).
- YAML carregado por `yaml.safe_load` (não permite tags arbitrárias).

### T4: XSS em e-mail / Markdown injection no Telegram
**Impacto**: execução de código no cliente.
**Mitigações**:
- Jinja2 com `autoescape=True` para HTML.
- `escape_markdown_v2` em todas as saídas Telegram.
- CSP no `<head>` de e-mails.
- Tags HTML perigosas (script, style, iframe) removidas com pré-pass + bleach.

### T5: Prompt injection via conteúdo coletado
**Impacto**: LLM produzir output malicioso ou ignorar instruções.
**Mitigações**:
- Conteúdo coletado vai dentro de `<context>...</context>`.
- Output do LLM validado por pydantic com `extra="forbid"`.
- Schema strict — campos não declarados rejeitados.
- LLM nunca modifica `original.*` (write-once enforced).

### T6: Tampering retroativo no audit log
**Impacto**: ocultar comandos executados.
**Mitigações**:
- Append-only por design (storage não expõe update/delete).
- Hash chain: cada entry referencia hash da anterior.
- `verify_chain` detecta substituição.
- `frozen=True` no pydantic model `AuditLogEntry`.

### T7: Vazamento de secret em log
**Impacto**: credencial exposta em logs ou exceções.
**Mitigações**:
- `redact_sensitive` como primeiro processor do `structlog`.
- 16 patterns conhecidos: Stripe, Google, Slack, GitHub, AWS, Telegram, JWT.
- Mensagens de erro genéricas para o cliente; detalhe técnico apenas em log estruturado.
- `pydantic.SecretStr` em todos os campos sensíveis.

### T8: Honeytokens
**Estado**: planejados (fase 2).
**Plano**: plantar credenciais falsas via [Canarytokens.org](https://canarytokens.org/).
Detecção em ms se alguém tentar usar.

## Pre-commit checks

`gitleaks`, `detect-secrets`, `bandit`, `ruff -S`, regex de literais conhecidos
(`scripts/check_secret_literals.py`). Sem `--no-verify`.

## CI security gates

`.github/workflows/security.yml`:
- bandit (HIGH/MEDIUM bloqueia merge)
- pip-audit (HIGH/CRITICAL bloqueia)
- gitleaks (qualquer detection bloqueia)
- detect-secrets (vs baseline)
- SBOM (cyclonedx) gerado a cada push em main

## Padrões herdados de pentest 2026-04-20 (CLAUDE.md Seção 7)

- ✅ Validação de `ownerId`
- ✅ App Check enforce
- ✅ Deploy de functions ANTES de migrar dados
- ✅ Bloqueio de `sk_live_`, `sk_test_`, `whsec_`, etc. no pre-commit
- ⚪ Email verify, MFA grace, anti trial-farming — N/A (single-user)

## Resposta a incidente (leak de secret)

1. **Imediato**: revogar a credencial no provedor.
2. **Imediato**: rotacionar (gerar nova).
3. **Auditoria**: revisar logs dos últimos 90 dias para uso indevido.
4. **Reescrita** (se vazou em commit): `git filter-repo` ou abandonar repo.
5. **Postmortem**: documentar em `docs/postmortems/YYYY-MM-DD-{slug}.md`.

## Relatórios de vulnerabilidade

Sistema de uso pessoal — sem programa público de bug bounty.
Para vulns descobertas pelo dono: documentar em `docs/postmortems/` + corrigir.
