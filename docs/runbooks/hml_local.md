# Homologação local (MonitorITCD)

Overlay deste repo sobre o canônico
`~/Projetos/Skill/compartilhado/HML-LOCAL.md`
(bloco `<!-- HML-LOCAL:begin v1 -->` em `AGENTS.md` / `CLAUDE.md`).

Regra permanente 2026-09-12: **HML = localhost**. Sem projeto Firebase de HML.

## Overlay dos 6 itens canônicos

| # | Canônico | Neste repo |
|---|---|---|
| 1 | HML = localhost; local cobre produção | `.env` → `demo-monitoritcd` + emuladores. Pipeline = `pytest` / `python -m monitoritcd.main run --dry-run`. Functions (`bot_webhook`, `proxy_br`, `canary_filter`) = Python/pytest (layout `functions/*` não é codebase Firebase CLI). |
| 2 | Bateria HML antes de `/produção`; UI = Playwright | Sem `/produção` neste alinhamento. Playwright **obrigatório** na primeira mudança de UI. Hoje N/A: repo headless (Telegram + Pages gerado por `scripts/build_dashboard.py`), sem app FE. |
| 3 | UI nova/alterada/corrigida: protótipo antes de fechar | Idem: protótipo para aprovação **antes** de fechar qualquer tarefa de UI. Sem UI aberta agora. |
| 4 | Frontend/UI só Antigravity (`agy`) | Só `agy`. Fallback só por `~/Projetos/Skill/compartilhado/llm-ranking.yaml` se agy impossível. Nunca Gemini CLI. |
| 5 | Contas teste automação + admin | Google `ailtonganem@gmail.com` (`OWNER_EMAIL` / `GMAIL_USER`). |
| 6 | Firebase só-HML: listar → excluir depois | **Suspenso neste repo** (Orca ADE 2026-09-12): **não apagar** `sefworkstation-hml` nem `sefworkstation-app`. Projeto `monitoritcd` (`.firebaserc`) = UNKNOWN — não consultar, não deploy, não apagar. |

## Paridade local × produção

| Função de produção | Como cobrir em localhost |
|---|---|
| Pipeline de coleta/classificação | `pytest` + `python -m monitoritcd.main run --dry-run` |
| Firestore (metadados, watches, audit) | Emulador `127.0.0.1:18080` (`demo-monitoritcd`) |
| Firebase Storage (HTML/PDF) | Emulador `127.0.0.1:18199` |
| Cloud Function `bot_webhook` | `python -m monitoritcd.bot.poller` e `functions/bot_webhook/test_main.py` |
| Cloud Function `proxy_br` | `functions/proxy_br/` + testes locais |
| Cloud Function `canary_filter` | `functions/canary_filter/` + testes locais |
| Dashboard GitHub Pages | HTML estático; mudança de UI exige protótipo + Playwright + só `agy` |

## Subir HML

```bash
firebase emulators:start --project demo-monitoritcd --only firestore,storage,auth,ui
python -m monitoritcd.main painel
# UI do painel (mesma origem da API): http://127.0.0.1:8765
# NÃO use http://127.0.0.1:4200 — neste host isso é o SEFWorkStation, não o MonitorITCD.
```

Alias Firebase HML: `.firebaserc` → `hml` = `demo-monitoritcd` (emulador). Auth emulator em `127.0.0.1:19099` para não colidir com o Auth do SEF na `9099`. O projeto remoto `monitoritcd` permanece intocado.

Não use só `ng serve` na `:4200` sem o proxy e sem o processo Python na `:8765`.
Detalhe: `docs/painel_ia_hml.md`.

Aba Orca `emuladores` já usa esse comando. UI: <http://127.0.0.1:14000>.

Portas dedicadas — a `8080` do Book é o Open WebUI, não o Firestore:
- Firestore `127.0.0.1:18080`
- Storage `127.0.0.1:18199`
- Hub `127.0.0.1:14400`

O `.env` local usa `FIREBASE_PROJECT_ID=demo-monitoritcd` e os hosts de emulador.
O SDK (`google-cloud-firestore` / `firebase-admin`) lê `FIRESTORE_EMULATOR_HOST`
e `FIREBASE_STORAGE_EMULATOR_HOST` e não fala com projeto remoto.

## O que não fazer

- Não apontar `.env` para `sefworkstation-hml`.
- Não apagar `sefworkstation-hml` nem `sefworkstation-app`.
- Projeto Firebase `monitoritcd` (`.firebaserc`) = UNKNOWN: não consultar, não deploy, não apagar.
- Sem `/produção` neste alinhamento. Sem contratar serviço. Sem excluir repo.
- Não alterar Functions, Rules, IAM nem rodar `deploy-functions.yml`.
