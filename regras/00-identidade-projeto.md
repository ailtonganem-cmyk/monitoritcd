# 00 — Identidade do projeto (MonitorITCD)

> Fonte da verdade sobre **o que é o projeto, quem manda e onde ele vive**.
> Este é um dos dois módulos por-projeto (o outro é o `40-regras-negocio.md`).

## O que é

- **Nome:** MonitorITCD
- **Descrição:** sistema autônomo que monitora mudanças legislativas, normativas
  e jurisprudenciais sobre **ITCD/ITCMD/ITD**, **Direito das Sucessões** e
  **Regime de Bens**, coletando de assembleias, SEFAZs, diários oficiais e
  tribunais, classificando por LLM e notificando o dono por e-mail e Telegram.
- **Natureza:** **uso pessoal, single-user, headless.** Sem multi-tenant, sem
  autenticação de terceiros, sem autocadastro, sem billing, sem redistribuição.
  Não há frontend web — a interface humana é e-mail + bot Telegram (`50`).
- **Escopo geográfico ativo:** **MG + fontes federais** (decisão do dono
  2026-07-08). Os YAMLs das demais 26 UFs permanecem no repositório,
  **desativados** via `active_uf: ["MG"]` no Firestore; reativar exige nova
  decisão do dono. Supersede o "MVP enxuto de 5 estados".
- **Tom das mensagens ao dono:** técnico-preciso, direto, sem floreio; pt-BR.

## Stack

- **Linguagem:** Python ≥ 3.11, type hints em todo código novo, async-first.
- **Coleta:** `httpx` (async — nunca `requests` síncrono), `beautifulsoup4` +
  `lxml`, `feedparser`, `pypdf` → `pdfplumber`, `bleach` (sanitização), `tenacity`.
- **Validação:** `pydantic` v2 (`SecretStr` para secrets) — em toda fronteira de
  processo (HTTP, DB, LLM, env, bot).
- **LLM:** Gemini 2.5 Flash primário, Groq (Llama 3.3) fallback (`40`).
- **Persistência:** Firestore (metadados) + Firebase Storage (HTML/PDF brutos) +
  `audit_log` com hash chain.
- **Execução:** GitHub Actions (cron `13 10 * * *` = 07:13 BRT, timeout 30 min) +
  Cloud Functions (`proxy_br`, `bot_webhook`, `canary_filter`) em
  `southamerica-east1`.
- **Saídas:** `jinja2` (`autoescape=True`), `python-telegram-bot` v21+ via webhook.
- **Observabilidade:** `structlog` JSON com redator de secrets; Healthchecks.io.
- **Qualidade:** `pytest` (+ `pytest-recording`, `hypothesis`, `syrupy`, `respx`),
  `ruff` (lint + format, regras `S`), `mypy --strict` em módulos críticos,
  `bandit`, `pip-audit`, `detect-secrets`, `gitleaks`, `mutmut`. Comandos e
  limiares: `70`.

Visão arquitetural completa (C4 + diagramas): `docs/ARCHITECTURE.md`.

## Pessoas autorizadas

| Pessoa | Papel | Permissões |
| --- | --- | --- |
| Ailton Ganem (`ailtonganem-cmyk` no GitHub) | Dono / decisor final — **único usuário** | Tudo: código, deploy, secrets, decisões |

Identificadores operacionais do dono (e-mail de destino, `chat_id` do Telegram)
vivem **apenas em variáveis de ambiente / GitHub Secrets** — nunca em arquivo
versionado.

## Regra de execução autônoma [decisão do dono, preservada de 2026-04]

**O agente é o único responsável pela implementação — o dono não executa tarefas
manuais.** Dentro da tarefa em curso, e com os gates verdes (`70`), o agente:

- instala ferramentas e dependências necessárias;
- configura serviços externos via API/CLI (`gh`, `firebase`, `gcloud`, `curl`);
- commita, faz push e dispara workflows;
- faz deploy de Cloud Functions e das rules.

**Isso não dissolve as NUNCAs nem a tabela perguntar × agir (`90`)** — billing,
aceitar termos, criar contas, delete em massa e `push --force` continuam
exigindo ordem expressa. **Único caso em que o dono executa:** tarefa
tecnologicamente impossível para o agente (login OAuth interativo, 2FA por SMS,
acesso físico a hardware, instalador com clique em popup) — que deve ser
**listada e justificada** a ele, nunca presumida.

## URLs e IDs canônicos

| Recurso | Valor |
| --- | --- |
| Repositório | `https://github.com/ailtonganem-cmyk/monitoritcd` (branch principal: `main`) |
| Projeto Firebase | `monitoritcd` |
| Região das Cloud Functions | `southamerica-east1` |
| Working directory canônico | `C:\Projetos\MonitorITCD` |
| Worktrees das tarefas | `C:\Projetos\MonitorITCD-worktrees\<id>` (fora do repo — `80`) |

GitHub Secrets em uso (nomes; valores nunca no repositório): `GEMINI_API_KEY`,
`GROQ_API_KEY`, `GMAIL_USER`*, `GMAIL_APP_PASSWORD`*, `EMAIL_RECIPIENT`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`,
`FIREBASE_SERVICE_ACCOUNT_JSON`, `FIREBASE_PROJECT_ID`,
`FIREBASE_STORAGE_BUCKET`, `HEALTHCHECKS_URL`.
*E-mail é canal **opcional**: credencial ausente desliga só o canal, nunca
derruba a coleta.

## Estrutura do repositório (mapa curto)

```
src/monitoritcd/{core,collectors,filters,llm,storage,notifiers,bot,security,observability,resilience}/
sources/{_federal,AC..TO}/*.yaml     # 27 entes; ativação é runtime, não código
functions/{proxy_br,bot_webhook,canary_filter}/
scripts/                             # operação: seed, backup, restore, doctor, verify
tests/{unit,integration,security,templates,e2e,cassettes}/
docs/{adr,runbooks,ufs,templates}/   # conhecimento durável
regras/                              # ESTE conjunto — fonte da verdade das regras
specs/                               # SPECs de Execução versionadas (10, 80)
_trabalho/                           # estado compartilhado por tarefa — gitignorado (30)
```
