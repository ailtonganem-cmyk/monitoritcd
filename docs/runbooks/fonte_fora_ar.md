# Runbook — Fonte fora do ar há ≥ 7 dias

> Sugestão #43 — runbook por cenário, mais específico que o `RUNBOOKS.md` raiz.

## Sintomas

- Bot `/status` mostra fonte na lista "stale".
- `report.failed_sources` contém o `source_id` repetidamente.
- Email de digest mostra "0 itens" para UF impactada.

## Diagnóstico (5 min)

1. Identificar `source_id` da fonte em log:
   ```bash
   gh run list --workflow=monitor.yml --limit=10
   gh run view <run_id> --log | grep "source.failed"
   ```
2. Tipo da falha:
   - `ConnectTimeout` → site fora do ar **ou** geo-restricted (e proxy_br falhou).
   - `ParseError` → layout do site mudou.
   - `403/404` → URL mudou ou bloqueio.

## Decisão

Use a árvore:

```
                Fonte fora ≥ 7d?
                       │
            ┌──────────┴──────────┐
            │                     │
       Geo-restricted?        ParseError?
            │                     │
       ┌────┴────┐           ┌────┴────┐
       │         │           │         │
   Sim/proxy   Não      Layout      URL mudou?
   ok?         (rede)   mudou?
       │                  │           │
       ▼                  ▼           ▼
   Investigar         Atualizar     Atualizar
   PROXY_BR_TOKEN    selectors      url no YAML
                     em YAML
```

## Ações

### A1 — Atualizar selectors HTML

```bash
# 1. Ler HTML manual:
curl -s -A "Mozilla/5.0" 'https://exemplo.gov.br/feed' > /tmp/page.html

# 2. Inspecionar com browser dev tools, identificar novo selector.

# 3. Editar YAML:
$EDITOR sources/{UF}/{fonte}.yaml

# 4. Re-rodar:
python -m monitoritcd.main run --source-id {source_id} --dry-run
```

### A2 — Marcar como `fragile`

Se layout muda toda semana, considere reduzir prioridade:

```yaml
# sources/{UF}/{fonte}.yaml
fragile: true  # reduz weight no prescore
```

### A3 — Silenciar temporariamente (último recurso)

Se a UF inteira está com problema:

```
/silenciar UF 14d
```

Deixa a equipe local resolver e reativa em 14 dias.

## Pós-incidente

Adicionar entrada em `docs/postmortems/` se levou > 1h ou se causa raiz é não-óbvia.

## Referências

- `src/monitoritcd/orchestrator.py:_collect_all` — isolamento por fonte
- `docs/SLO.md` — S3 (taxa de sucesso por fonte ≥ 90%)
