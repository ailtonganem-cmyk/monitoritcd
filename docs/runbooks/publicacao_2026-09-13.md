# Publicação 2026-09-13 — painel HML, Pages e Cloud Functions

Registro operacional do que foi publicado nesta data. Sem valores de secret.

## SHA

`main` = `9c706fe1765365829a45b51992861f2db2ce16f1`

PRs mergeados nesta frente: #51 (painel/HML/IA), #52 e #53 (workflow de deploy).

## O que está no ar

| Superfície | Onde | Como verificar |
|---|---|---|
| Código | GitHub `main` | SHA acima |
| Dashboard | https://ailtonganem-cmyk.github.io/monitoritcd/ | HTTP 200 |
| `proxy_br` | GCP projeto `monitoritcd`, `southamerica-east1` | URI `https://proxy-br-nd3pdtc4gq-rj.a.run.app` — GET sem token → 401 |
| `canary_filter` | idem | `https://canary-filter-nd3pdtc4gq-rj.a.run.app` — GET sem token → 401 |
| `bot_webhook` | idem | `https://bot-webhook-nd3pdtc4gq-rj.a.run.app` — GET → 405 |

Functions atualizadas em 2026-09-13 ~20:24–20:27 UTC via `gcloud` autenticado como `ailtonganem@gmail.com`, fonte do SHA `9c706fe`. Env já existente nas Functions **não** foi regravado.

## HML (localhost)

Não há Firebase de HML. Emuladores usam o prefixo `demo-monitoritcd`.

```bash
firebase emulators:start --project demo-monitoritcd --only firestore,storage,auth,ui \
  --import=.emulator-data --export-on-exit=.emulator-data
python -m monitoritcd.main painel --host 127.0.0.1 --port 8765
```

- Painel: http://127.0.0.1:8765 — botão **Entrar local (HML)** (`ailtonganem@gmail.com`).
- Não usar http://127.0.0.1:4200 neste host (é o SEFWorkStation).
- Auth emulator: `127.0.0.1:19099` (não a `9099` do SEF).
- UI emuladores: http://127.0.0.1:14000.

Detalhe do painel/IA: `docs/painel_ia_hml.md`. Overlay HML: `docs/runbooks/hml_local.md`.

## Armadilha: Actions aponta para o projeto errado

O workflow `.github/workflows/deploy-functions.yml` usa `secrets.FIREBASE_PROJECT_ID` e `secrets.FIREBASE_SERVICE_ACCOUNT_JSON`.

Em 2026-09-13 o dispatch falhou com 403: a SA `monitor-cron@…` tentou `gcloud services enable` e `gcloud functions deploy` no projeto cujo **número** é o do **SEFWorkStation** (`sefworkstation-app`), não o `monitoritcd`.

Não alterar esse par de secrets sem uma SA **do** projeto `monitoritcd`. Publicação comprovada: `gcloud functions deploy … --project=monitoritcd` com a conta humana do founder.

Não apagar `sefworkstation-app` nem `sefworkstation-hml`.

## Telegram webhook — pendente

`setWebhook` **não** foi feito. O `TELEGRAM_BOT_TOKEN` do `.env` local não é um token válido (`getMe` → 401). O workflow `setup-telegram-webhook.yml` também leria o projeto do secret (errado).

Com o token de **produção** (GitHub Secret, não o stub local):

```bash
# url da Function publicada
# https://bot-webhook-nd3pdtc4gq-rj.a.run.app
```

`secret_token` = `TELEGRAM_WEBHOOK_SECRET` de produção.

## Recusas / residual

- `functions/proxy_br/main.py` ainda usa `follow_redirects=True` (SSRF). Código não foi alterado nesta publicação.
- Painel `/api/coleta` devolve o comando `python -m monitoritcd.main run`; não dispara o pipeline no servidor HTTP.
- Checkout local `agent/governanca-enxuta-monitoritcd` pode estar sujo; a `main` publicada é o SHA acima. Não `git add .`.
