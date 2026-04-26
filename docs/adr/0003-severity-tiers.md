# ADR 0003 — Severity tiers e canais de notificação

**Status**: Accepted
**Data**: 2026-04-26 (registro retroativo)

## Contexto

Notificar 50-200 itens/dia ao dono é spam. Precisamos hierarquia.

## Decisão

Quatro tiers determinísticos mapeados de `relevancia` (0-10):

| Tier | Relevância | Canal | Estratégia |
|---|---|---|---|
| 🔴 CRITICO | 9-10 | Telegram **push imediato** | 1 mensagem por item |
| 🟠 ALTA | 7-8 | Telegram digest + Email | Destaque no digest |
| 🟡 NORMAL | 5-6 | Telegram digest + Email | Item no digest |
| 🟢 BAIXA | 3-4 | Email digest semanal | Sem Telegram |
| ⚫ DESCARTADO | 0-2 | Nenhum | Marcado e arquivado |

Mapeamento em `src/monitoritcd/notifiers/severity.py` (puro, deterministic).

## Consequências

- Push imediato apenas para mudança de alíquota / decisão STF/STJ vinculante.
- Digest preserva contexto agregado.
- DESCARTADO ainda persiste no Firestore (auditoria) — só não notifica.

## Referências

- `src/monitoritcd/notifiers/severity.py`
- `src/monitoritcd/filters/llm_classifier.py:49` (SEVERITY_THRESHOLDS)
