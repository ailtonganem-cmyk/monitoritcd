# Runtime Firebase (GitHub só repositório)

Produção: projeto GCP/Firebase **`monitoritcd`** (Blaze). HML continua localhost (`demo-monitoritcd` + emuladores).

## Superfícies

| Superfície | URL / recurso |
|---|---|
| Painel | https://monitoritcd.web.app |
| API do painel | Function `painel_api` (`southamerica-east1`) |
| Pipeline diária | Function `monitor_cron` + Cloud Scheduler `monitor-cron-0233/1013/1447` |
| Já existentes | `proxy_br`, `canary_filter`, `bot_webhook` |

Login: Google Sign-In, allowlist **somente** `ailtonganem@gmail.com`. Em produção o botão HML local está desligado (`ENV=production`).

## OAuth (passo único no Console)

A Function `painel_api` precisa de `GOOGLE_OAUTH_CLIENT_ID` (cliente Web) com origens:

- `https://monitoritcd.web.app`
- `https://monitoritcd.firebaseapp.com`
- `http://127.0.0.1:8765` (HML)

Criar em: https://console.cloud.google.com/apis/credentials?project=monitoritcd  
Tipo: **Aplicativo da Web**. Depois:

```bash
# CLIENT_ID = identificador do cliente OAuth tipo Web (Console > Credenciais).
gcloud functions deploy painel_api --gen2 --region=southamerica-east1 --project=monitoritcd \
  --update-env-vars=GOOGLE_OAUTH_CLIENT_ID="$CLIENT_ID"
```

Não commitar o client secret. O client ID pode ir só na env da Function.

Ativar Authentication no Console Firebase (Get started) e o provedor Google, com domínio autorizado `monitoritcd.web.app`.

## Redeploy

```bash
npm --prefix apps/painel run build
python scripts/deploy_firebase_runtime.py
firebase deploy --only hosting,firestore:rules --project monitoritcd
```

O script copia as env já publicadas em `bot_webhook` e **só adiciona** chaves novas (`OPENROUTER`, `DEEPSEEK`, `OPENCODE`) a partir de `~/Projetos/APIs`. Não substitui `GEMINI_API_KEY` nem as demais já existentes.

## Cron

Schedules UTC (iguais às antigas do GitHub Actions): `33 2`, `13 10`, `47 14`.  
Reserva manual: `gh workflow run monitor.yml` (sem `schedule`).
