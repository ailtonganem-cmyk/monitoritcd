# ADR 0004 — Audit log com hash chain

**Status**: Accepted
**Data**: 2026-04-26 (registro retroativo)

## Contexto

Bot Telegram pode mutar estado (ativar/desativar UFs, marcar docs, silenciar).
Precisamos detectar tampering — incluindo do próprio dono se conta for
comprometida.

## Decisão

Audit log append-only com hash chain (estilo blockchain simplificado):
- Cada `AuditLogEntry` referencia `prev_hash` da entry anterior.
- Verificação: `audit.verify_chain()` recomputa toda a chain.
- Em runtime: `orchestrator` valida 20 últimas entries no início de cada execução
  (Sugestão #25 deste plano).

## Consequências

**Positivas**:
- Tampering retroativo detectado.
- Custo: 1 SHA-256 por append + 1 leitura de prev hash.

**Negativas**:
- Não previne tampering — só detecta.
- Genesis hash (`"0" * 64`) é convenção; documentar.

## Referências

- `src/monitoritcd/storage/audit_log.py`
- `scripts/verify_audit_chain.py`
- `tests/unit/test_bot_audit.py`
