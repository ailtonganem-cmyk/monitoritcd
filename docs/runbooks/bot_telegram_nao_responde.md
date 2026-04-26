# Runbook — Bot Telegram não responde

## Sintomas

- Comandos `/status`, `/buscar`, etc. enviam mas bot silente.
- Webhook não chama Cloud Function.

## Diagnóstico (3 min)

1. Cloud Function viva?
   ```bash
   gcloud functions describe bot_webhook --region=us-central1
   ```
2. Logs recentes da Function:
   ```bash
   gcloud functions logs read bot_webhook --region=us-central1 --limit=50
   ```
3. Webhook configurado?
   ```bash
   curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
   ```
   Resposta deve mostrar URL apontando para a Cloud Function.

## Ações

### A1 — Webhook desconfigurado

```bash
gh workflow run setup-telegram-webhook.yml
```

### A2 — Cloud Function indisponível

Re-deploy:
```bash
gh workflow run deploy-functions.yml
```

### A3 — Token Telegram comprometido/rotacionado

1. BotFather: `/newtoken` → gera novo.
2. Atualizar GitHub Secret `TELEGRAM_BOT_TOKEN`.
3. Re-deploy: `gh workflow run deploy-functions.yml`.
4. Re-configurar webhook: `gh workflow run setup-telegram-webhook.yml`.
5. Audit: `audit_log` deve ter entry de rotação.

### A4 — Rate limit por comando travando

Sugestão #24 implementou limites apertados. Em testes pode-se exceder rapidamente.
Aguardar 60s ou testar com chat_id alternativo (somente em ambiente de dev).

## Pós-incidente

- Validar que Healthchecks.io ping de bot ainda chega.
- Adicionar uptime check explícito do webhook se incidente recorrente.

## Referências

- `functions/bot_webhook/main.py`
- `src/monitoritcd/bot/auth.py`
