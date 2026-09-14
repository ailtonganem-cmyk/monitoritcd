# Runtime Firebase (GitHub só repositório)

Produção: projeto GCP/Firebase **`monitoritcd`** (Blaze). HML continua localhost (`demo-monitoritcd` + emuladores).

## Superfícies

| Superfície | URL / recurso |
|---|---|
| Painel | https://monitoritcd.web.app |
| API do painel | Function `painel_api` (`southamerica-east1`) |
| Pipeline diária | Function `monitor_cron` + Cloud Scheduler `monitor-cron-0233/1013/1447` |
| Já existentes | `proxy_br`, `canary_filter`, `bot_webhook` |

Login: Google via Firebase Auth (`signInWithRedirect` em `https://monitoritcd.firebaseapp.com`). `web.app` redireciona para esse host (authDomain e cookie no mesmo domínio). Allowlist **somente** `ailtonganem@gmail.com`. Em produção o botão HML local está desligado (`ENV=production`).

O painel não usa popup GIS: o COOP do Google bloqueia `window.closed`. O redirect autorizado é `https://monitoritcd.firebaseapp.com/__/auth/handler`. O backend valida o ID token Google (`tokeninfo` + `GOOGLE_OAUTH_CLIENT_ID`) e, se não for GIS, o JWT do Firebase Auth.

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
