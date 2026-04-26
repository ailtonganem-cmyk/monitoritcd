# PLAN.md — Plano de Execução do MVP

> Este documento orquestra a construção do MonitorITCD em **fases sequenciais e gateadas**.
> Cada fase tem deliverables específicos, testes obrigatórios e Definition of Done (DoD).
> **Não avançar para fase N+1 sem completar fase N.**
>
> Ideias do `IDEAS.md` selecionadas pelo dono (com `[x]`) são absorvidas neste plano
> **na fase apropriada** — não onde está numerada.

## Convenções

- 🟦 Em planejamento • 🟨 Em andamento • 🟩 Concluída • 🟥 Bloqueada • ⬜ Não iniciada
- Cada fase tem um **Gate** — checklist de saída.
- Cada arquivo criado tem teste correspondente antes do gate.
- Princípios canônicos do `CLAUDE.md` valem em **todas** as fases.

---

## Tracker de fases

| Fase | Nome | Status |
|---|---|---|
| 0 | Foundation | 🟩 Concluída |
| 1 | Core domain models & security primitives | 🟩 Concluída |
| 2 | Collector framework | 🟩 Concluída |
| 3 | Filtering pipeline | 🟩 Concluída |
| 4 | Storage (Firebase) | 🟩 Concluída |
| 5 | Notification (Email + Telegram) | 🟩 Concluída |
| 6 | Bot Telegram interativo | 🟩 Concluída |
| 7 | Orchestration & CI/CD | 🟩 Concluída |
| 8 | Cobertura MVP — 5 UFs + federais | 🟩 Concluída |
| 9 | Operations — backup, dashboard, monitoring | 🟩 Concluída |
| 10 | Pre-deploy validation | 🟩 Concluída |
| 11 | Backlog IDEAS.md (pós-MVP) | 🟦 Em planejamento |
| 12 | 50 melhorias hardening (sem custo) | 🟩 Concluída — 2026-04-26 |

---

## Fase 0 — Foundation 🟩 CONCLUÍDA

**Deliverables entregues**:
- [x] `CLAUDE.md`, `IDEAS.md` (com 500 checkboxes), `PLAN.md`, `README.md`
- [x] `pyproject.toml` (deps completas, ruff, mypy, pytest, coverage configurados)
- [x] `.gitignore`, `.pre-commit-config.yaml`, `.env.example`, `.secrets.baseline`
- [x] `firestore.rules` (deny all)
- [x] `scripts/check_secret_literals.py` (bloqueio determinístico)
- [x] `.github/workflows/security.yml` (SAST + secrets + deps + SBOM)
- [x] `.github/workflows/tests.yml` (lint + mypy + pytest + coverage + mutation)
- [x] Virtualenv criado, deps instaladas, ruff verde
- [x] Estrutura de diretórios completa

**Ideias do IDEAS.md absorvidas nesta fase**: nenhuma — fase puramente de fundação.

---

## Fase 1 — Core domain models & security primitives 🟩 CONCLUÍDA

**Deliverables entregues**:
- [x] `src/monitoritcd/core/limits.py` — fonte da verdade de input_limits (52 stmts, 100% cov)
- [x] `src/monitoritcd/core/models.py` — pydantic models com `OwnerScoped`, `extra="forbid"`, `frozen=True` em RawItem/Source/AuditLog (147 stmts, 92% cov)
- [x] `src/monitoritcd/core/config.py` — `Settings` com `SecretStr`, `__repr__` mascarado (33 stmts, 97% cov)
- [x] `src/monitoritcd/core/sanitize.py` — `bleach` + pré-pass para script/style/iframe (33 stmts, 100% cov)
- [x] `src/monitoritcd/security/url_validator.py` — anti-SSRF: scheme/host whitelist, RFC1918, link-local, metadata (45 stmts, 91% cov)
- [x] `src/monitoritcd/security/log_redactor.py` — structlog processor para tokens (23 stmts, 94% cov)
- [x] `src/monitoritcd/security/markdown_escape.py` — Telegram MarkdownV2 + split por bytes UTF-8 (40 stmts, 98% cov)
- [x] `tests/unit/test_limits.py` (9 testes)
- [x] `tests/unit/test_models.py` (26 testes)
- [x] `tests/unit/test_config.py` (9 testes)
- [x] `tests/unit/test_sanitize.py` (21 testes)
- [x] `tests/security/sanitization/test_html_sanitization.py` (24 testes — OWASP XSS cheat sheet)
- [x] `tests/security/ssrf/test_url_validator.py` (32 testes)
- [x] `tests/security/test_log_redactor.py` (29 testes)
- [x] `tests/security/test_markdown_escape.py` (34 testes)

**Gate (DoD) atingido**:
- [x] 184 testes passando (100% pass rate)
- [x] Cobertura global 95.04% (gate ≥ 95%)
- [x] `mypy --strict` Success: 0 errors em 9 arquivos
- [x] `ruff check`: All checks passed
- [x] `bandit`: 0 issues HIGH/MEDIUM
- [x] Property-based tests com `hypothesis` em sanitize, URL validator, redactor, markdown escape
- [x] OWASP XSS Cheat Sheet — 20 payloads neutralizados

**Ideias do IDEAS.md absorvidas**: implícito a infra da #338 (detecção de injection), parte dos #306-#322 (bases de audit), backbone para #461-#485 (testes).

---

## Fase 2 — Collector framework ⬜

**Goal**: ABC de coletor, schema YAML, parsers genéricos (RSS, HTML), primeiro coletor real (LexML).

**Deliverables**:
- `src/monitoritcd/core/base_collector.py` — ABC `BaseCollector` (async)
- `src/monitoritcd/core/source_loader.py` — carrega/valida YAML em `sources/`
- `src/monitoritcd/collectors/__init__.py`
- `src/monitoritcd/collectors/generic_rss.py`
- `src/monitoritcd/collectors/generic_html.py`
- `src/monitoritcd/collectors/lexml.py` — primeira fonte real (mais simples)
- `sources/_federal/lexml.yaml`
- Testes:
  - `tests/unit/test_base_collector.py`
  - `tests/integration/test_lexml.py` (com cassette VCR)
  - `tests/unit/test_source_loader.py` (validação de schema)

**Gate (DoD)**:
- [ ] LexML retorna ≥ 1 item ITCD em ambiente de teste
- [ ] Cassette VCR gravado e versionado
- [ ] Validação de URL anti-SSRF aplicada na carga de YAML
- [ ] Cobertura ≥ 95% em `collectors/`

**Ideias do IDEAS.md absorvidas**: #30 (LexML SRU), as demais fontes ficam para Fase 8.

---

## Fase 3 — Filtering pipeline ⬜

**Goal**: filtro de keywords, pré-score heurístico, classifier LLM (Gemini com batch).

**Deliverables**:
- `src/monitoritcd/filters/__init__.py`
- `src/monitoritcd/filters/keywords.py`
- `src/monitoritcd/filters/prescore.py` — heurística (densidade × autoridade × frescor)
- `src/monitoritcd/filters/llm_classifier.py` — Gemini com batch + Groq fallback + retries
- `src/monitoritcd/dedup.py` — dedup em camadas (URL > num_ato > fuzzy)
- Testes:
  - `tests/unit/test_keywords.py`
  - `tests/unit/test_prescore.py`
  - `tests/integration/test_llm_classifier.py` (cassettes; nunca API real em CI)
  - `tests/security/prompt_injection/test_classifier.py` — payloads maliciosos
  - `tests/unit/test_dedup.py`

**Gate (DoD)**:
- [ ] Classifier produz JSON válido em 100% dos casos de teste
- [ ] Prompt injection: input "ignore previous instructions..." → output ainda schema-válido
- [ ] LLM **não modifica** dados originais (validar verbatim de números/nomes)
- [ ] Cobertura 100% em `filters/` e `dedup.py`

**Ideias do IDEAS.md absorvidas**: #51-#54 (pré-score), #55 (cache), e outras conforme marcadas.

---

## Fase 4 — Storage (Firebase) ⬜

**Goal**: persistência em Firestore com `owner_id`, raw em Storage, audit log.

**Deliverables**:
- `src/monitoritcd/storage/__init__.py`
- `src/monitoritcd/storage/firestore_store.py` — CRUD com `assert_owner` + App Check
- `src/monitoritcd/storage/firebase_storage.py` — upload de HTML/PDF
- `src/monitoritcd/storage/audit_log.py` — append-only com hash chain
- `firestore.rules` — `deny all` para clients não-admin
- Testes:
  - `tests/integration/test_firestore_store.py` (Firebase emulator)
  - `tests/integration/test_firebase_storage.py` (emulator)
  - `tests/security/test_owner_isolation.py` — owner errado é rejeitado
  - `tests/unit/test_audit_log.py` — hash chain válida

**Gate (DoD)**:
- [ ] Firebase emulator roda em CI
- [ ] `assert_owner` impede leitura/escrita cross-owner
- [ ] Audit log: tentativa de modificar entry passada falha
- [ ] `firestore.rules` deployadas com `deny all`

**Ideias do IDEAS.md absorvidas**: #306-#314 (audit log core), conforme marcações.

---

## Fase 5 — Notification (Email + Telegram) ⬜

**Goal**: envio de digest com severity tiers, templates jinja2, snapshot tests.

**Deliverables**:
- `src/monitoritcd/notifiers/__init__.py`
- `src/monitoritcd/notifiers/severity.py` — mapeamento relevância → tier → canal
- `src/monitoritcd/notifiers/email_notifier.py` — SMTP Gmail
- `src/monitoritcd/notifiers/telegram_notifier.py` — Bot API + escape MarkdownV2 + split 4096
- `src/monitoritcd/notifiers/templates/email.html.j2`
- `src/monitoritcd/notifiers/templates/telegram.md.j2`
- Testes:
  - `tests/templates/test_email_render.py` — snapshot
  - `tests/templates/test_telegram_render.py` — snapshot + edge cases
  - `tests/security/test_markdown_injection.py`
  - `tests/security/test_xss_in_email.py`

**Gate (DoD)**:
- [ ] E-mail HTML válido por html5lib + CSS inline
- [ ] Telegram: split correto > 4096 chars, escape de chars especiais
- [ ] Snapshots aprovados; mudanças requerem revisão explícita
- [ ] Smoke test: enviar 1 e-mail real para o dono em ambiente sandbox

**Ideias do IDEAS.md absorvidas**: #96-#170 conforme marcações; severity tiers já no MVP.

---

## Fase 6 — Bot Telegram interativo ⬜

**Goal**: webhook + comandos básicos (`/start`, `/help`, `/status`, `/buscar`, `/observar`, `/silenciar`, `/estados`, `/confirmar`).

**Deliverables**:
- `src/monitoritcd/bot/__init__.py`
- `src/monitoritcd/bot/auth.py` — validação `chat_id`, rate limit, 2-step token
- `src/monitoritcd/bot/handlers.py` — comandos
- `src/monitoritcd/bot/webhook.py` — entry point Cloud Function
- `firebase.json` (se usar Functions) ou alternativa (cron-driven polling se quiser evitar Functions)
- Testes:
  - `tests/security/input_validation/test_bot_commands.py` — fuzz com hypothesis
  - `tests/unit/test_auth.py` — chat_id, rate limit, token efêmero
  - `tests/integration/test_handlers.py`

**Gate (DoD)**:
- [ ] `chat_id` errado é rejeitado em 100% dos testes de fuzz
- [ ] Rate limit funciona (10/min)
- [ ] Token de confirmação expira em 60s e é single-use
- [ ] Pelo menos 5 comandos básicos respondendo

**Ideias do IDEAS.md absorvidas**: #171-#220 conforme marcações; mínimo MVP é #171, #172, #173, #174, #202-#204.

---

## Fase 7 — Orchestration & CI/CD ⬜

**Goal**: `main.py` entry point, GitHub Actions cron, Healthchecks.io ping, dedup integrada.

**Deliverables**:
- `src/monitoritcd/main.py` — orquestrador (`--dry-run`, `--reprocess`, `--source-id`, `--uf`)
- `.github/workflows/monitor.yml` — cron 10:13 UTC + workflow_dispatch
- `.github/workflows/tests.yml` — pytest + coverage + mutation (semanal)
- `scripts/seed_active_states.py` — popula Firestore com defaults na primeira execução
- Testes:
  - `tests/e2e/test_full_pipeline.py` — pipeline completa em sandbox

**Gate (DoD)**:
- [ ] Workflow `monitor.yml` roda manualmente com sucesso (`workflow_dispatch`)
- [ ] Healthchecks.io recebe pings
- [ ] E2E test passa em CI

**Ideias do IDEAS.md absorvidas**: a determinar.

---

## Fase 8 — Cobertura MVP (5 UFs + federais) ⬜

**Goal**: YAMLs e cassettes para SP, RJ, MG, RS, DF + Conjur, Migalhas, JOTA federais.

**Deliverables**:
- `sources/_federal/conjur.yaml`, `migalhas.yaml`, `jota.yaml`, `stf.yaml`, `stj.yaml`
- `sources/SP/alesp.yaml`, `sefaz.yaml`, `doe.yaml`
- `sources/RJ/alerj.yaml`, `sefaz.yaml`, `doe.yaml`
- `sources/MG/almg.yaml`, `sefaz.yaml`, `doe.yaml`
- `sources/RS/alrs.yaml`, `sefaz.yaml`, `doe.yaml`
- `sources/DF/cldf.yaml`, `sefaz.yaml`, `dodf.yaml`
- `docs/ufs/SP.md`, `RJ.md`, `MG.md`, `RS.md`, `DF.md` — alíquota e regime atual
- Cassettes para cada
- (UFs restantes: YAMLs criados, mas inativos — Fase pós-MVP)

**Gate (DoD)**:
- [ ] Cada fonte retorna ≥ 1 item em ambiente de teste
- [ ] Tabela das 27 UFs no README atualizada (5 ativas)
- [ ] Coleta diária real funcionando

**Ideias do IDEAS.md absorvidas**: itens #1-#50 prioritários (5 UFs + federais).

---

## Fase 9 — Operations ⬜

**Goal**: backup mensal, retention policy, dashboard básico, observabilidade.

**Deliverables**:
- `.github/workflows/backup.yml` — backup mensal cifrado com `age`
- `scripts/backup.py`, `scripts/restore.py`
- `scripts/cleanup_retention.py` — purge descartados após 90d
- Dashboard estático em `docs/dashboard/` (GH Pages)
- `SECURITY.md` — threat model
- `RUNBOOKS.md` — procedimentos operacionais
- Honeytokens (#323, #324)

**Gate (DoD)**:
- [ ] Backup automatizado roda 1x e é verificável
- [ ] Restore manual testado
- [ ] Dashboard publicado em GH Pages

**Ideias do IDEAS.md absorvidas**: #406-#420 (backup), #221, #355-#356 (dashboard), #341-#365 (métricas) conforme marcações.

---

## Fase 10 — Pre-deploy validation ⬜

**Goal**: validação final antes de cron rodar em produção.

**Deliverables**:
- 3 dias de execução manual via `workflow_dispatch` sem falhas
- Cobertura ≥ 95% global, 100% críticos
- 0 falhas em testes de segurança
- README final com setup completo
- Tabela das 27 UFs (5 ativas, 22 prontas-para-ativar)

**Gate (DoD)**:
- [ ] Tudo verde
- [ ] `firestore.rules` aplicadas
- [ ] App Check ativo
- [ ] Notificações chegando ao dono
- [ ] Cron habilitado

---

## Como o dono interage com este plano

1. **Marcar ideias em `IDEAS.md`** com `[x]` nas ideias desejadas.
2. Cada PR menciona qual ideia(s) está implementando (`Closes IDEAS.md #123`).
3. Ao marcar uma ideia, o trabalho **é absorvido na fase apropriada** — não em qualquer momento.
   - Coletor de UF nova → Fase 8 ou pós-MVP.
   - Comando de bot → Fase 6 (se MVP) ou pós-MVP.
   - Métrica/dashboard → Fase 9.
   - Etc.
4. Itens marcados em IDEAS.md mas que ainda não cabem em fase atual ficam na fila;
   serão abordados quando a fase correspondente for ativada.

## Fase 11 — Backlog IDEAS.md (pós-MVP) 🟦

**Goal**: depois do gate da Fase 10, abrir programa estruturado de absorção
do backlog em `IDEAS.md` priorizado por valor × esforço.

**Pré-requisitos** (gate da Fase 10):
- [x] MVP no ar com cron 3 dias verde
- [x] Sistema operacional (audit log, Cloud Functions, dashboard)
- [x] Fase A-C de validação pós-MVP concluída (cobertura 100% críticos, smoke real)

**Como funciona**:
1. Dono marca itens em `IDEAS.md` com `[x]` priorizando.
2. Cada item vira issue (ou bundle de issues) com label `idea-absorbed`.
3. PRs referenciam `Closes IDEAS.md #N` e seguem CLAUDE.md.
4. Gate de cada PR: testes, cobertura ≥ 95%, sem regressão de segurança.

**Subfases candidatas** (a priorizar conforme dono escolhe):
- 11.1 — 12 UFs restantes sem cobertura legislativa (BA, MA, AP, PA, RN, SE, SC, TO, RR, AC já em re-verificação trimestral).
- 11.2 — WhatsApp via Meta Cloud API (alternativa ao Telegram).
- 11.3 — Reprocessamento histórico (comando `--reprocess` está pronto; falta UI/bot).
- 11.4 — Melhorias do `--dry-run` (separar leitura Firestore × escrita InMemory).
- 11.5 — Funcionalidades avançadas marcadas em `IDEAS.md` (ML scoring, summarization customizada, alertas por tópico jurídico, etc.).

**Não-goal**: implementar tudo do IDEAS.md. Backlog é fonte de candidatos,
não checklist obrigatório. Triagem semestral pelo dono filtra o que segue.

---

## Notas operacionais

- **Princípios canônicos do CLAUDE.md são obrigatórios** em toda fase.
- **Cobertura de testes** verificada em cada PR; CI bloqueia se cair.
- **Segurança não é fase** — é transversal. Cada fase adiciona testes de segurança específicos.
- **Documentação** é deliverable, não opcional.

---

## Fase 12 — 50 melhorias hardening (sem custo) 🟩 CONCLUÍDA — 2026-04-26

Hardening abrangente em 8 categorias, sem despesa financeira.

### Categorias entregues

- **A** Qualidade & Tipagem (1-7): mypy expandido, ruff regras adicionais, vulture, radon, interrogate piso 90.
- **B** Testes (8-17): mutation testing expandido, hypothesis fuzz, smoke E2E, snapshot Firestore, diff-cover, regression LLM, HTML5 strict.
- **C** Segurança (18-26): CodeQL, actionlint, dependabot, OSSF Scorecard, rate limit por comando, audit chain runtime, fuzz URLs.
- **D** Observabilidade (27-32): Prometheus textfile, DLQ, source heartbeat, SLO formal.
- **E** CI/CD & DevEx (33-38): cache pip, matrix Python, commitlint, doctor.py, lint semântico YAML.
- **F** Documentação (39-43): ADRs 0002-0005, mermaid pipeline, STRIDE threat model, tabela 27 UFs, runbooks decompostos.
- **G** Performance & Resiliência (44-47): circuit breaker per-source, Aho-Corasick keyword matcher.
- **H** Domínio Jurídico (48-50): regex pré-LLM, validador citações CC, cluster temático multi-UF.

Detalhes completos em `CHANGELOG.md` seção `[Unreleased] — 50 melhorias gratuitas`.
