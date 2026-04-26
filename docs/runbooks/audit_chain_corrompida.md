# Runbook — Audit chain corrompida

## Sintomas

- `report.errors` contém `audit_chain_corruption: ...` (Sugestão #25).
- `scripts/verify_audit_chain.py` falha.
- Bot `/status` indica "audit chain inconsistente".

## Severidade

🔴 **CRÍTICO**. Audit chain quebrada = potencial tampering ou bug no append path.

## Diagnóstico (10 min)

1. Verificar última entry válida:
   ```bash
   python scripts/verify_audit_chain.py
   ```
   Saída mostra a posição em que a chain quebrou.

2. Investigar logs em torno do timestamp:
   ```bash
   gh run list --workflow=monitor.yml --limit=20
   gh run view <run_id> --log | grep "audit\|append_audit"
   ```

3. Confirmar se há mutations em `audit_log/` fora do `AuditLog.append`:
   - `firestore.rules` está em `deny all` para clientes não-admin?
   - Service account foi rotacionada recentemente?

## Ações

### A1 — Sem evidência de tampering (bug)

Append de entry futura criou chain inconsistente (race ou crash mid-append):

1. Backup completo do audit_log atual:
   ```bash
   python scripts/backup.py --collection audit_log
   ```
2. Identificar entry quebrada (output do verify).
3. Decisão: deixar quebra documentada (entry seguinte usa hash da quebrada
   como prev). Adicionar `postmortem` em `docs/postmortems/`.

### A2 — Suspeita de tampering

1. **Não delete nada.** Audit é evidência.
2. Auditar:
   - Quem usou a service account nas últimas 24h?
   - GitHub Audit Log: quem fez push em `main` nas últimas 24h?
3. Rotacionar **imediatamente**:
   - Service account Firebase.
   - `TELEGRAM_BOT_TOKEN` (cobertura única do dono — assumir comprometida).
   - Todas as chaves API.
4. Postmortem completo em `docs/postmortems/`.

## Pós-incidente

Documentar em `docs/postmortems/YYYY-MM-DD-audit-chain.md`:
- Timeline.
- Causa raiz (bug ou intent).
- Mitigação aplicada.
- Mudanças preventivas.

## Referências

- ADR 0004 — `docs/adr/0004-audit-hash-chain.md`
- `src/monitoritcd/storage/audit_log.py`
- `scripts/verify_audit_chain.py`
