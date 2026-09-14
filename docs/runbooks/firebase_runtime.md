# Runtime Firebase (GitHub só repositório)

Produção: projeto GCP/Firebase **`monitoritcd`** (Blaze). HML continua localhost (`demo-monitoritcd` + emuladores).

## Superfícies

| Superfície | URL / recurso |
|---|---|
| Painel | https://monitoritcd.web.app |
| API do painel | Function `painel_api` (`southamerica-east1`) |
| Pipeline diária | Function `monitor_cron` + Cloud Scheduler `monitor-cron-0233/1013/1447` |
| Já existentes | `proxy_br`, `canary_filter`, `bot_webhook` |

Login: Google via Firebase Auth (`signInWithPopup`, com `signInWithRedirect` se o popup falhar), allowlist **somente** `ailtonganem@gmail.com`. Em produção o botão HML local está desligado (`ENV=production`).

O painel não usa o botão GIS no `web.app` (origem JavaScript do cliente OAuth não é gravável por API). O fluxo usa o redirect já autorizado `https://monitoritcd.firebaseapp.com/__/auth/handler`. O backend continua validando o ID token Google com `GOOGLE_OAUTH_CLIENT_ID` na Function `painel_api`.

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
