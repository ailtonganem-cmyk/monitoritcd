# Runbook — Quota LLM esgotada (Gemini + Groq)

## Sintomas

- `report.errors` contém `classify_deferred (X items): quota exhausted`.
- Items com `status=PENDING` acumulando em Firestore.
- Bot `/status` mostra "X items pending".

## Diagnóstico

1. Verificar quota Gemini:
   - Console GCP → APIs → Generative Language API → Quotas
   - Free tier: 15 RPM, 1.500 req/dia.
2. Verificar quota Groq:
   - Console Groq → Settings → Usage.
3. Ver qual provedor falhou primeiro:
   ```bash
   gh run view <run_id> --log | grep "fallback\|quota"
   ```

## Ações imediatas

### A1 — Aguardar reset

Free tiers resetam em 24h (UTC midnight para Gemini).
Próxima execução do cron pegará pendentes automaticamente
(`status=PENDING` continua na fila).

### A2 — Reprocessamento manual

Após reset:
```bash
python -m monitoritcd.main reprocess --since 2026-04-01
```

### A3 — Otimizar pré-filtro

Se quota é estourada com frequência, pré-filtro está deixando passar lixo:

1. Inspecionar items rejeitados:
   ```python
   docs = await storage.list_documentos(status=PENDING)
   for d in docs[:20]:
       print(d.original.titulo_raw)
   ```
2. Se há padrões claros (ex: "convocação para audiência X"), adicionar
   keyword de exclusão em `filters/keywords.py`.

### A4 — Tunar pré-score cutoff

`DEFAULT_CUTOFF=0.3` em `filters/prescore.py`. Subir para 0.4 reduz volume,
mas pode deixar passar coisas relevantes — testar com cassettes.

## Pós-incidente

Considerar:
- Mudar para tier pago do Gemini (Tier 1: 1.000 RPM, 10.000 req/dia).
- Implementar cache de classificações (`content_hash` → `LLMResult`).

## Referências

- ADR 0002 — `docs/adr/0002-llm-gemini-groq.md`
- `src/monitoritcd/llm/fallback.py`
