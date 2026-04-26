# MonitorITCD

Sistema autônomo de monitoramento de mudanças legislativas, normativas e jurisprudenciais
brasileiras em **3 áreas correlatas**:

- **ITCD/ITCMD/ITD** — tributo estadual sobre heranças e doações.
- **Direito das Sucessões** — Direito Civil (CC arts. 1.784+).
- **Regime de Bens** — Direito Civil (CC arts. 1.639-1.688).

> 🟢 **MVP completo** — 10 fases concluídas. Veja [PLAN.md](PLAN.md) para o tracker
> de fases e [CLAUDE.md](CLAUDE.md) para arquitetura, princípios canônicos e convenções.

## Características

- 🤖 **Coleta diária** (cron 07:13 BRT via GitHub Actions) de Assembleias, SEFAZs, Diários Oficiais e tribunais superiores.
- 🧠 **Classificação por LLM** (Gemini 2.5 Flash + Groq fallback) — preserva conteúdo verbatim.
- 🔔 **Notificações multi-canal** (Telegram + e-mail) com tiers de severidade.
- 🤖 **Bot Telegram interativo** com comandos para busca, ativação de UFs, watch list.
- 🗂️ **Schema com separação estrita** entre dados originais (write-once) e metadados gerados por LLM.
- 🛡️ **Defense-in-depth** — sanitização total, validação `owner_id`, App Check enforce, anti-SSRF.
- 💸 **100% free tier** — Firebase Spark, GitHub Actions, Gemini, Groq, Telegram.
- 🔒 **Single-user** — uso pessoal, sem multi-tenancy.
- 📊 **Backup mensal cifrado** via `age` → Google Drive.
- 📋 **Audit log com hash chain** — tampering detectável.

## Princípios canônicos

Três princípios inegociáveis (detalhados em [CLAUDE.md](CLAUDE.md#-princípios-canônicos-fontes-da-verdade)):

1. 🔒 **Nunca confiar no frontend** — backend valida tudo, sempre.
2. 📏 **`input_limits` obrigatórios** — `MAX_LENGTH/ITEMS/DEPTH/BYTES/DURATION`.
3. 🔐 **Secrets PROIBIDOS em código fonte** — sem exceção, sem `--no-verify`.

## Stack

- **Linguagem**: Python 3.11+
- **Storage**: Firebase (Firestore + Storage + audit log)
- **LLM**: Google Gemini 2.5 Flash (primary) + Groq (fallback)
- **Orquestração**: GitHub Actions (cron 10:13 UTC)
- **Notificação**: Gmail SMTP + Telegram Bot API
- **Bot**: webhook via Cloud Function
- **Testes**: pytest + hypothesis + syrupy + pytest-recording (444 testes, 96% cobertura)

## Setup

### Pré-requisitos

- Python 3.11+
- Conta no [Firebase](https://console.firebase.google.com/) (Spark plan)
- Chave do [Google AI Studio](https://aistudio.google.com/) (Gemini)
- Conta no [Groq](https://console.groq.com/) (fallback LLM)
- Bot do Telegram via [@BotFather](https://t.me/BotFather)
- Conta Gmail com [App Password](https://myaccount.google.com/apppasswords)
- (Opcional) [Healthchecks.io](https://healthchecks.io/)
- (Opcional) Chave [age](https://github.com/FiloSottile/age) para backups

### Instalação local

```bash
git clone <repo-url>
cd MonitorITCD

python -m venv .venv
source .venv/bin/activate     # Linux/macOS
# .venv\Scripts\activate      # Windows

pip install -e ".[dev]"

pre-commit install
cp .env.example .env
# Edite .env com seus secrets

pre-commit run --all-files
pytest
```

### Smoke test (sem rede real)

```bash
python -m monitoritcd.main run --dry-run --source-id lexml-federal
```

### Setup detalhado

Ver [RUNBOOKS.md](RUNBOOKS.md) — passo-a-passo de:
- Setup inicial completo
- Adicionar nova fonte
- Ativar UF
- Rotacionar secret
- Restaurar de backup
- Investigar fontes que pararam

## Arquitetura

```
┌──────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ GitHub Actions   │────▶│ Collectors       │────▶│ Filter (kw+LLM) │
│ (cron 10:13 UTC) │     │ (UFs ativas+fed) │     │ Gemini 2.5 Flash│
└──────────────────┘     └──────────────────┘     └────────┬────────┘
                                                            │
        ┌──────────────────────┐    ┌──────────────────┐    │
        │ Telegram + Email     │◀───│ Notifier         │◀───┤
        │ (severity tiers)     │    │ (sanitizer)      │    │
        └──────────┬───────────┘    └──────────────────┘    │
                   │                                         ▼
                   │                            ┌──────────────────────┐
        ┌──────────▼─────────┐                  │ Firebase             │
        │ Bot interativo     │─────────────────▶│ • Firestore          │
        │ /comandos do dono  │                  │ • Storage (HTML/PDF) │
        └────────────────────┘                  │ • Audit log (chain)  │
                                                └──────────────────────┘
```

## Cobertura de fontes

> Fonte da verdade detalhada: [docs/sources_status.md](docs/sources_status.md).

### Federais ativas (8 fontes)

| Fonte | Tipo | Notas |
|---|---|---|
| **LexML Legislação** | API SRU | Cobre federal + 26 estados + DF (legislação sancionada) |
| **LexML Jurisprudência** | API SRU | STF + STJ + TJs estaduais |
| **Câmara Deputados** | API REST v2 | PLs/PLPs/PECs federais sobre ITCD/sucessões (Reforma Tributária etc.) |
| **Senado Federal** | API `/processo` | Matérias do Senado, vetos presidenciais |
| **JOTA** | RSS | Notícias jurídicas tributárias |
| **STF notícias** | RSS oficial | Decisões do STF |
| **STJ notícias** | RSS oficial | Decisões do STJ |

### Proposições/notícias estaduais (15 UFs ativas)

| UF | Coletor | Plataforma |
|---|---|---|
| **MG** | ALMGCollector (custom) | API JSON `dadosabertos.almg.gov.br` |
| **PR** | ALEPCollector (custom) | API JSON via POST (`webservices.assembleia.pr.leg.br`) |
| **PE** | ALEPECollector (custom) | API XML `dadosabertos.alepe.pe.gov.br` |
| **MS** | GenericRSSCollector | RSS notícias `https://www.al.ms.gov.br/RSS` (substituto parcial) |
| **AC, AL, AM, CE, ES, GO, MT, PB, PI, RO, RR** | SAPLCollector (genérico) | API REST padronizada Interlegis |

### UFs sem coletor de proposições (12)

Para essas UFs, **leis sancionadas continuam cobertas via LexML**. A lacuna é
apenas proposições em tramitação que ainda não viraram lei.

Investigação 2026-04-26 (em [docs/sources_status.md](docs/sources_status.md)
e [docs/fontes_alternativas_uf.md](docs/fontes_alternativas_uf.md))
documenta por que cada UF não tem API pública: ALESP/SP requer VIEWSTATE,
ALERJ/RJ usa Lotus Notes legacy, Alesc/SC pede integração privada, etc.

**Re-investigação trimestral** automatizada via routine remota (cron
`0 14 1 1,4,7,10 *`) verifica se alguma das 12 UFs passou a oferecer
API pública e abre PR com achados.

**Total**: 20 fontes ativas. Cobertura legislativa via LexML atinge **27 entes
federativos + federal**. Cobertura de proposições/notícias estaduais: **15 UFs (56%)**.

Veja [docs/ufs/](docs/ufs/) para particularidades por UF (alíquotas, lei principal, peculiaridades).

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Arquitetura, princípios canônicos, convenções, threat model |
| [PLAN.md](PLAN.md) | Plano de execução por fases (10 fases — todas concluídas no MVP) |
| [SECURITY.md](SECURITY.md) | Threat model, ameaças mapeadas, resposta a incidente |
| [RUNBOOKS.md](RUNBOOKS.md) | Procedimentos operacionais passo-a-passo |
| [IDEAS.md](IDEAS.md) | 500 sugestões de funcionalidades futuras (com checkboxes) |
| `docs/ufs/{UF}.md` | Particularidades por estado |

## Comandos úteis

```bash
# Lint & format
ruff check .
ruff format .

# Type check
mypy

# Security
bandit -c pyproject.toml -r src/
detect-secrets scan --baseline .secrets.baseline
python scripts/check_secret_literals.py $(git ls-files)

# Testes
pytest                                     # tudo
pytest -m unit                             # só unitários
pytest -m security                         # só segurança
pytest -m integration                      # integração
pytest -m templates                        # snapshot tests
pytest --cov=src/monitoritcd --cov-branch  # com cobertura

# Mutation testing (semanal)
mutmut run --paths-to-mutate src/monitoritcd/filters

# Pipeline em dry-run
python -m monitoritcd.main run --dry-run

# Pipeline para uma fonte específica
python -m monitoritcd.main run --dry-run --source-id lexml-federal

# Backup manual
AGE_PUBLIC_KEY=age1... python scripts/backup.py --output backup.json.gz.age

# Cleanup retenção
python scripts/cleanup_retention.py --dry-run
```

## Bot Telegram — comandos

- `/start` ou `/help` — saudação + lista de comandos
- `/status` — saúde do sistema, UFs ativas, contadores
- `/buscar <termo> [topico=itcd|sucessoes|regime_bens]` — busca filtrada
- `/topicos` — lista divisões temáticas
- `/estados listar` — UFs ativas
- `/estados ativar <UF>` — ativa monitoramento
- `/estados desativar <UF>` — requer confirmação 2 passos
- `/confirmar <token>` — confirma operação destrutiva

## Princípios em código

| Princípio | Materialização |
|---|---|
| Backend não confia | `extra="forbid"` em todo modelo pydantic |
| input_limits | `core/limits.py` — 52 constantes aplicadas em 14 modelos |
| Secrets fora do código | pre-commit (gitleaks + detect-secrets + regex de literais) |
| Defense-in-depth | URL validator + sanitize HTML + Markdown escape + log redactor |
| LLM não modifica | Schema com `original.*` (write-once) vs `llm.*` (reprocessável) |
| `owner_id` enforcement | `assert_owner` em todas mutations + queries scoped |
| Audit imutável | Hash chain + `frozen=True` em entries |

## Métricas atuais

- **444 testes** passando (100%)
- **96% cobertura global** (gate ≥ 95%)
- **0 erros** em `mypy --strict`, `ruff`, `bandit -ll`
- **0 falhas** em testes de segurança (sanitização, SSRF, prompt injection, markdown injection)
- **OWASP XSS Cheat Sheet** — 20 payloads neutralizados

## Licença

Uso pessoal. Sistema proprietário do dono. Sem licença pública.

## Contribuição

Single-user. PRs do próprio dono via Claude Code seguindo padrões em [CLAUDE.md](CLAUDE.md).
