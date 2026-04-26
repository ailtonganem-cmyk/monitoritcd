# Changelog

Todas as mudanças notáveis ao MonitorITCD são documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — 50 melhorias gratuitas (2026-04-26)

> Hardening abrangente: qualidade de código, testes, segurança, observabilidade,
> CI/CD, documentação, performance e domínio jurídico. Sem custo financeiro.

### Adicionado

#### Qualidade e tipagem (Sugestões 1-7)
- `mypy --strict` expandido: + `notifiers/severity`, `filters/keywords`,
  `filters/prescore`, `dedup`.
- `ruff` regras adicionais: `PERF`, `LOG`, `BLE`, `PTH`, `ERA`.
- `vulture` (dead code) e `radon`/`xenon` (complexidade) no CI.
- `interrogate` piso elevado de 80 → 90.
- `disallow_untyped_decorators=true` no mypy.

#### Testes (Sugestões 8-17)
- Mutation testing expandido para `notifiers/email`, `notifiers/telegram`,
  `core/sanitize`, `bot/auth`, `bot/handlers`.
- Diff coverage no PR (`diff-cover`) com gate ≥ 95% na diff.
- Matrix testing Python 3.11/3.12/3.13 no CI.
- Smoke E2E (`tests/e2e/`) com InMemoryStorage + FakeLLM.
- Snapshot testing Firestore schema (`tests/unit/test_firestore_schema_snapshot.py`).
- Regression tests do prompt LLM (`tests/llm_regression/`).
- Validação HTML5 strict em templates de email.
- Fuzz adversarial de URLs e source_loader (hypothesis).

#### Segurança (Sugestões 18-26)
- Workflow CodeQL (`security-extended,security-and-quality`).
- Workflow `actionlint` para os próprios YAMLs de CI.
- `dependabot.yml` (Python + GitHub Actions).
- OSSF Scorecard workflow.
- Rate limit por comando (`PerCommandRateLimiter`): mutativos 5/min, read-only 30/min.
- Validação runtime do audit chain no `orchestrator.run_pipeline`.
- Lint semântico de YAMLs em `sources/` (`scripts/lint_sources_yaml.py`).

#### Observabilidade (Sugestões 27-32)
- `monitoritcd.observability.prometheus_textfile`: métricas em formato textfile.
- `monitoritcd.observability.dlq.DeadLetterQueue`: fila para itens com falha persistente.
- `monitoritcd.observability.source_heartbeat.SourceHeartbeat`: tracking per-source.
- `docs/SLO.md`: 5 SLOs explícitos (S1-S5).

#### CI/CD e DevEx (Sugestões 33-38)
- Cache pip por hash de `pyproject.toml` no GH Actions.
- Workflow commitlint (Conventional Commits).
- `scripts/doctor.py`: diagnóstico de setup local.
- Lint semântico de YAMLs em `sources/` no security workflow.

#### Documentação (Sugestões 39-43)
- ADRs: 0002 (Gemini/Groq), 0003 (severity tiers), 0004 (audit hash chain),
  0005 (proxy_br geo-restricted).
- `docs/THREAT_MODEL.md` com framework STRIDE.
- `docs/UFS_STATUS.md`: tabela das 27 UFs.
- Diagrama Mermaid do pipeline em `docs/ARCHITECTURE.md`.
- Runbooks decompostos: `fonte_fora_ar.md`, `llm_quota_esgotada.md`,
  `bot_telegram_nao_responde.md`, `audit_chain_corrompida.md`.

#### Performance e resiliência (Sugestões 44-47)
- `monitoritcd.resilience.CircuitBreaker`: circuit breaker per-source.
- `monitoritcd.resilience.KeywordMatcher`: matcher Aho-Corasick + fallback.

#### Domínio jurídico (Sugestões 48-50)
- `monitoritcd.filters.extractors`: extração regex pré-LLM (Lei, Decreto, IN, etc.).
- `monitoritcd.filters.citation_validator`: validação de citações de artigos do CC.
- `monitoritcd.filters.thematic_cluster`: cluster de docs em UFs distintas.

### Mudado

- `pyproject.toml`: `[tool.interrogate] fail-under = 90` (era 80).
- `pyproject.toml`: `[tool.mutmut].paths_to_mutate` expandido.
- `pyproject.toml`: ruff `select` adiciona `PERF, LOG, BLE, PTH, ERA`.
- `bot/auth.py`: novo `PerCommandRateLimiter` paralelo ao global.
- `orchestrator.py`: validação leve de audit chain no início do run.

## [Backlog] — Cobertura IDEAS.md (em andamento)

### Adicionado

#### Categorias 1-12 (ver IDEAS.md)
- **Categoria 1**: 27 fontes novas (cobertura territorial completa 27 UFs + Conjur, Migalhas, Receita, CONFAZ, IBET, IBPT, SciELO, BDTD, PGFN, AGU, TJs estaduais, TIT-SP).
- **Categoria 2**: `thematic_detector.py` com 22 detectores heurísticos PT-BR (alíquota, sanção/veto, relator, revogação, recursos, tema STF/STJ, modulação, temas específicos).
- **Categoria 3**: 4 templates de e-mail (default, compacto, executivo, newsletter), dark mode automático, anexos CSV/JSON, ranking, saudação dinâmica, reply-to.
- **Categoria 4**: Inline keyboards Telegram, pin/edit/chat_action, agrupamento UF/tipo, DND noturno, `setup_bot_commands.py`.
- **Categoria 5**: 6 canais multi-channel (Discord/Ntfy/Slack/Pushover/Matrix/Webhook), feeds RSS/Atom/JSON, ICS calendar.
- **Categoria 6**: 17 handlers bot novos (silenciar, fontes, quota, export, diff, historico, comentar, lembrar, etc.).
- **Categoria 7**: `analytics.py` com 12 funções (trending, top sources/UFs, gap, alíquotas, maturity, sefaz proactivity, sazonalidade).
- **Categoria 8**: `search.py` com 14 funções (faceted, boolean, fuzzy, regex, more_like_this, normalize_act_number).
- **Categoria 9**: `watches.py` engine + 7 templates (alíquota_sp, holding_familiar, pec_itcd, modulação, etc.).
- **Categoria 10**: `pii_redactor.py`, `injection_detector.py`, `verify_audit_chain.py`.
- **Categoria 11**: `metrics.py` com ExecutionMetrics + Prometheus/JSON exporters.
- **Categoria 12**: `source_health.py`, `source_validators.py`.

### Documentação

- `docs/CONTRIBUTING.md`
- `docs/ARCHITECTURE.md` (C4 levels)
- `CHANGELOG.md` (este arquivo)

## [Histórico anterior]

Antes desta release, o projeto seguia commits direto na main com PRs ao longo
das Fases 0-11 do PLAN.md. Ver `git log` para histórico detalhado.

Marcos relevantes:
- **2026-04-20**: pentest aplicado (CLAUDE.md §7 padrões adicionais).
- **2026-04-25**: 14 UFs cobertas, 4 Cloud Functions, expansion regional.
- **2026-04-26**: Fases A-D validação concluídas; PRs #6-#10 mergeados.
