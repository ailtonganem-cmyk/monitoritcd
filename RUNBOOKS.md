# RUNBOOKS.md — Procedimentos operacionais

Procedimentos passo-a-passo para operações no MonitorITCD. Documento vivo;
atualizar após cada incidente ou nova tarefa operacional.

## Índice

1. [Setup inicial](#setup-inicial)
2. [Adicionar nova fonte](#adicionar-nova-fonte)
3. [Ativar UF](#ativar-uf)
4. [Rotacionar secret](#rotacionar-secret)
5. [Restaurar de backup](#restaurar-de-backup)
6. [Aplicar retenção manual](#aplicar-retenção-manual)
7. [Reprocessar período](#reprocessar-período)
8. [Investigar fonte que parou de coletar](#investigar-fonte-que-parou-de-coletar)
9. [Cron silenciou (sem ping em healthchecks)](#cron-silenciou)
10. [Quota Firestore esgotada](#quota-firestore-esgotada)
11. [Iniciar bot interativo (polling worker)](#iniciar-bot-interativo-polling-worker)

---

## Iniciar bot interativo (polling worker)

Bot por padrão é **outbound-only** (cron envia digests). Para usar comandos
interativos (`/status`, `/buscar`, etc.), rode o polling worker:

```bash
# Foreground
python -m monitoritcd.bot.poller

# Background (Linux/macOS)
nohup python -m monitoritcd.bot.poller > bot.log 2>&1 &

# Windows (separar console)
start /B pythonw -m monitoritcd.bot.poller
```

O worker faz long-poll de 30s a `getUpdates`, valida `chat_id`, despacha
para handlers e responde via Bot API. Stop com Ctrl+C ou `kill <pid>`.

Para deixar rodando 24/7 num server pessoal:
- Linux: criar serviço systemd em `/etc/systemd/system/monitoritcd-bot.service`
- macOS: launchd plist em `~/Library/LaunchAgents/`
- Windows: Task Scheduler com "Run whether user is logged on or not"

---

## Setup inicial

1. Criar projeto Firebase (Spark plan).
2. Habilitar Firestore (modo nativo) e Storage.
3. Gerar service account JSON: Project Settings → Service Accounts → Generate.
4. Criar bot Telegram via [@BotFather](https://t.me/BotFather), obter token.
5. Mandar `/start` ao bot e capturar seu `chat_id` (loga no servidor).
6. Configurar Gmail App Password: https://myaccount.google.com/apppasswords
7. Obter Gemini API key: https://aistudio.google.com/apikey
8. (Opcional) Healthchecks.io — criar check, copiar URL.
9. Configurar GitHub Secrets (todos os listados em `.env.example`).
10. Aplicar `firestore.rules`: `firebase deploy --only firestore:rules`.
11. Trigger primeira execução: `gh workflow run monitor.yml --field dry_run=true`.

## Adicionar nova fonte

1. Criar `sources/{UF}/{nome}.yaml` ou `sources/_federal/{nome}.yaml`.
2. Definir `parser`, `url`, `keywords_required`, `selectors` (se HTML).
3. Validar YAML: `pytest tests/unit/test_source_loader.py`.
4. Smoke test: `python -m monitoritcd.main run --dry-run --source-id <id>`.
5. Verificar log para falhas (selectors, URL).
6. Se OK: marcar `ativo: true` e `fragile: false` no YAML.
7. Commit + PR.

## Ativar UF

1. Confirmar que `sources/{UF}/*.yaml` existem e foram smoke-testados.
2. No bot Telegram: `/estados ativar SP`.
3. No próximo cron, fontes da UF entram na coleta.
4. Verificar primeira execução: `/status`.

## Rotacionar secret

**Periodicidade**: a cada 90 dias.
**Trigger**: lembrete mensal via Telegram (script futuro).

Para cada secret:
1. Gerar novo no provedor (Gemini Studio, BotFather, Gmail, etc.).
2. Atualizar GitHub Secret correspondente.
3. Atualizar `.env` local se for usar dev.
4. Revogar credencial antiga no provedor.
5. Trigger workflow manual para validar: `gh workflow run monitor.yml`.

Secrets a rotar:
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `GMAIL_APP_PASSWORD`
- `TELEGRAM_BOT_TOKEN` (raro — só se vazou)
- `TELEGRAM_WEBHOOK_SECRET`
- `FIREBASE_SERVICE_ACCOUNT_JSON` (rotação de chave do SA)
- `AGE_PUBLIC_KEY` / chave privada associada (cuidado: precisa restaurar backups antigos)

## Restaurar de backup

⚠️ Operação destrutiva.

1. Baixar backup `.age` do Drive (pasta GDRIVE_FOLDER_ID).
2. Confirmar identity file com chave privada `age` em local seguro.
3. Dry-run primeiro:
   ```bash
   python scripts/restore.py backup-2026-04.age --identity ~/.age/identity --dry-run
   ```
4. Verificar contagem de docs no output.
5. Executar real:
   ```bash
   python scripts/restore.py backup-2026-04.age --identity ~/.age/identity
   ```
6. Confirmar interativamente (digitar `sim`).
7. Validar `/status` no bot.

## Aplicar retenção manual

Normalmente roda automaticamente, mas para forçar:

```bash
# Dry-run
python scripts/cleanup_retention.py --dry-run

# Real
python scripts/cleanup_retention.py
```

Política aplicada (CLAUDE.md):
- Documentos descartados (relevancia < 5): 90 dias.
- Audit log: 1 ano.
- Execuções: 6 meses.

## Reprocessar período

Quando prompt do LLM melhora ou modelo é trocado:

```bash
# Para uma UF específica nos últimos 90d (futuro — ainda não implementado)
gh workflow run monitor.yml \
  --field dry_run=false \
  --field source_id=lexml-federal
```

Para reprocessamento amplo, edit `main.py` para adicionar `--reprocess --since YYYY-MM-DD`.

## Investigar fonte que parou de coletar

**Sintoma**: fonte aparece em `report.failed_sources` consecutivamente.

1. Verificar no bot: `/status` → quais fontes estão ativas.
2. Reproduzir localmente:
   ```bash
   python -m monitoritcd.main run --dry-run --source-id <id>
   ```
3. Diagnóstico comum:
   - **404**: URL mudou → atualizar YAML.
   - **403/timeout em CI mas OK local**: GitHub Actions runner US bloqueado → considerar proxy ou rodar via VPS dedicada.
   - **0 itens com seletors atuais**: layout mudou → ajustar `selectors`.
   - **RSS malformado**: `feedparser` engasgou; fallback para HTML scraping.
4. Marcar `ativo: false` temporariamente se a fonte estiver totalmente quebrada.

## Cron silenciou

**Sintoma**: alerta do Healthchecks.io ("nenhum ping nas últimas X horas").

1. Verificar GitHub Actions: https://github.com/{user}/monitoritcd/actions/workflows/monitor.yml
2. Causas comuns:
   - **Cota de minutos esgotada** (raro em repo público; possível em privado).
   - **Workflow falhou silenciosamente** (logs do runner).
   - **`schedule:` desativado** após 60 dias de inatividade do repo (push para reativar).
3. Disparar manualmente: `gh workflow run monitor.yml`.
4. Se o problema persistir, verificar `secrets` (algum vazio ou expirado).

## Quota Firestore esgotada

**Sintoma**: erros `RESOURCE_EXHAUSTED` em logs.

1. Verificar uso atual: Firebase Console → Firestore → Usage.
2. Identificar o que consumiu: `audit_log` é provavelmente o culpado se for write.
3. Mitigações:
   - Forçar `cleanup_retention.py`.
   - Rever queries que fazem N+1 reads.
   - Considerar export de audit antigo para Storage (mais barato).
4. Se persistir, esperar reset diário (00:00 UTC).
