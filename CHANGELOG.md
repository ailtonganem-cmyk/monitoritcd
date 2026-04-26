# Changelog

Todas as mudanças notáveis ao MonitorITCD são documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — Cobertura IDEAS.md (em andamento)

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
