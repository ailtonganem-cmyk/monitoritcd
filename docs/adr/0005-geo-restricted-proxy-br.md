# ADR 0005 — Fallback Cloud Function southamerica-east1 para fontes geo-restritas

**Status**: Accepted
**Data**: 2026-04-26 (registro retroativo de decisão de 2026-04-25)

## Contexto

Vários portais .gov.br bloqueiam IPs de fora do Brasil. GH Actions runners
ficam nos EUA. Sintoma: ConnectTimeout/ConnectError em fontes específicas
(ALMG é o caso recorrente), com sucesso em testes locais.

## Decisão

- Campo `geo_restricted: true` no YAML da fonte.
- `BaseCollector.fetch()` em ConnectTimeout/ConnectError direto faz fallback
  via Cloud Function `proxy_br` em `southamerica-east1` (free tier suficiente).
- Cloud Function valida whitelist (`.gov.br`, `.jus.br`, `.leg.br`) +
  auth via `X-Proxy-Token`.
- Reserva técnica: worker local Windows
  (`scripts/install_local_monitor_task.ps1`) com `--only-geo-restricted`.

## Consequências

**Positivas**:
- Fontes geo-restritas voltam a funcionar.
- Custo zero (Cloud Functions free tier: 2M invocações/mês).

**Negativas**:
- 1 hop adicional de latência.
- Mais um secret (`PROXY_BR_TOKEN`) para rotacionar.

## Referências

- `functions/proxy_br/main.py`
- `src/monitoritcd/core/base_collector.py` (lógica de fallback)
- `.github/workflows/deploy-functions.yml`
