# Jev Act — CRITICO vs digest (Pacote 4)

**Modo:** `JEV_MODE=act` (default). Wrapper exit **2** = deny → degradar CRITICO→digest no `notify_documents`.
Jev down → **fail-open** (mantém push). Contrato: `JEV-SESSAO.md` §12 + `ACT-ON.md`.

## Pontos de chamada

| Peça | Path |
|------|------|
| Wrapper | `~/Projetos/Skill/compartilhado/jev-implementacao-20260919/wrappers/monitor-itcd-shadow.sh` |
| Decide | `…/lib/jev-act-decide.py --gate critico` |
| Questions | `…/templates/monitor-itcd-critico.yaml` |
| Runtime | `src/monitoritcd/observability/jev_shadow_critico.py` → `filter_criticos_for_notify` |
| Logs | `shadow-logs/monitor-itcd.jsonl`, `act-logs/monitor-itcd.jsonl` |

## Comportamento

1. Cada doc `CRITICO` passa pelo wrapper antes do push.
2. **deny** (digest_only / need_more / confidence ≤70% no gate critico) → vai para digest, sem push imediato.
3. **allow** / fail-open → push CRITICO como antes.
4. Desligar: `MONITORITCD_JEV_SHADOW=0` ou `JEV_MODE=shadow` (só log, exit≠2 por act).

Jev **não** gera ementa/código e **não** autoriza `/produção`.
