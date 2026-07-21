# MonitorITCD — Guia para Codex

Sistema autônomo de monitoramento de mudanças legislativas, normativas e jurisprudenciais
relacionadas ao **ITCD/ITCMD/ITD** (Imposto sobre Transmissão Causa Mortis e Doação) nos
27 entes federativos brasileiros (26 estados + DF).

**Sistema de uso pessoal (single-user)** — uso exclusivo do dono. Sem multi-tenant, sem
autenticação de terceiros, sem redistribuição.

> Este arquivo orienta o trabalho do Codex neste repositório. Mantenha-o atualizado
> conforme decisões arquiteturais forem tomadas.

## ⚖️ Regra de execução autônoma

**O Codex é o único responsável pela implementação.** O dono não executa
tarefas manuais. Codex:

- Não pede autorização prévia para implementações dentro do escopo do projeto.
- Instala ferramentas necessárias quando possível (via npm, pip, curl + binários).
- Configura serviços externos via APIs/CLIs (`gh`, `firebase`, `gcloud`, curl).
- Toma decisões arquiteturais alinhadas com os princípios canônicos abaixo.
- Comita, faz push e dispara workflows livremente.

**Único caso em que o dono executa**: tarefas **tecnologicamente impossíveis**
para o Codex — login OAuth interativo no browser, aprovações 2FA por SMS,
acesso físico a hardware, instalação de software que exige clique em popup. Essas
tarefas devem ser **explicitamente listadas e justificadas** ao dono.

Decisões registradas em AGENTS.md/PLAN.md/IDEAS.md são vinculantes para sessões futuras.

## 🇧🇷 Idioma da conversa

**Toda comunicação com o dono é em Português Brasileiro (PT-BR).** Inclui:

- Mensagens em chat (respostas, perguntas, status reports).
- Mensagens de commit, PR descriptions, issue comments.
- Comentários em código quando úteis (raros, conforme princípio "comments só quando o WHY não é óbvio").
- Logs de erro voltados ao usuário, mensagens do bot Telegram.

**Permanece em inglês**: identificadores de código (variáveis, funções, classes,
módulos), nomes de tipos/enums internos, mensagens de erro técnicas que vão para
stack traces, dependências de bibliotecas externas em inglês.

Ao gerar mensagens de exceção que serão exibidas ao dono (ex: handlers de bot,
relatórios de pipeline), priorizar PT-BR.

---

## 🛡️ Princípios Canônicos (Fontes da Verdade)

Estes três princípios são **inegociáveis** e prevalecem sobre qualquer outra decisão de design,
prazo ou conveniência. Se entrarem em conflito com algo: **ganha o princípio.** Reabra o design.

Toda implementação, code review e teste deve verificar conformidade com eles.

### 🔒 Princípio 1 — Nunca confiar no frontend

Backend valida tudo, sempre. **Cliente é hostil por padrão.** Inclui:

- O bot Telegram (mesmo que `chat_id` confira — Telegram pode ter o token comprometido).
- Webhooks externos (assinatura é verificada antes de qualquer parsing).
- Conteúdo coletado de fontes (HTML, PDF, RSS são entradas não confiáveis).
- Configuração YAML (validada por pydantic na carga; URLs por whitelist anti-SSRF).
- O próprio dono operando o sistema.

**Regras de implementação:**
- Validação dupla — no recebimento da entrada **e** antes de persistir.
- Nenhuma decisão de autoridade tomada no cliente; tudo conferido no backend.
- Rate limiting em todas as superfícies (mesmo "internas").
- Timeout obrigatório em todas as chamadas externas.
- Mensagens de erro genéricas para o cliente; detalhe técnico só em log estruturado.
- Sem exceção "porque é só pra mim".

📌 Detalhe operacional: **Seção 7 (Segurança & Sanitização)**.

### 📏 Princípio 2 — `input_limits` obrigatórios

Toda entrada tem limites explícitos no backend. **Excedeu = rejeita.** Nunca trunca silenciosamente.

| Limite | Aplicação | Exemplo no MonitorITCD |
|---|---|---|
| `MAX_LENGTH` | Strings | título ≤ 500, comando bot ≤ 256, URL ≤ 2048 |
| `MAX_ITEMS` | Listas/arrays | tags por doc ≤ 20, watches por dono ≤ 100 |
| `MAX_DEPTH` | Objetos aninhados | JSON do LLM ≤ 5 níveis, YAML config ≤ 6 |
| `MAX_BYTES` | Payloads | HTML coletado ≤ 5 MB, PDF ≤ 20 MB, request body ≤ 1 MB |
| `MAX_DURATION` | Timeouts | HTTP req 30s, LLM call 60s, função 540s |

**Regras de implementação:**
- Pydantic `Field(max_length=N, max_items=N)` em **todo** modelo de entrada — sem exceção.
- Validação acontece no boundary (HTTP → modelo); falha = HTTP 400 / log + abort.
- Limites configurados centralizado em `core/limits.py`, importados onde precisar.
- Limites são **propriedade do backend** — não derivam do que o cliente envia.
- Excedeu = rejeita com mensagem genérica + log estruturado completo no servidor.

📌 Detalhe operacional: **Seção 7 (Padrões adicionais — Input limits obrigatórios)**.

### 🔐 Princípio 3 — Política de secrets: PROIBIDO em código fonte

Nenhum secret, key, token, senha, chave de API ou credencial em arquivo versionado.
**Nunca. Sem exceção. Sem `--no-verify`.**

**Onde secrets podem estar:**

| Local | Permitido? | Notas |
|---|---|---|
| GitHub Secrets | ✅ | CI/CD; única fonte para produção |
| Variável de ambiente local (`.env`) | ✅ | Apenas dev local; `.env` em `.gitignore` |
| Firebase Functions config | ✅ | `firebase functions:config:set` |
| Secret Manager (GCP) | ✅ | Fase futura; gerenciamento centralizado |
| Arquivos `.py`, `.yaml`, `.json`, `.md` | ❌ | **Nunca**, mesmo em "test", "example", "fixture" |
| Comentários, docstrings | ❌ | **Nunca** |
| Logs, mensagens de erro, exceções | ❌ | **Nunca** — redator filtra antes |
| Mensagens de bot, e-mails | ❌ | **Nunca** |

**Em código:**
- Sempre `pydantic.SecretStr`, `os.environ[...]` ou loader explícito (`config.get_secret(...)`).
- `__repr__`/`__str__` em modelos de config sobrescritos para mascarar (`"***"`).
- Filtros `structlog` redigem tokens conhecidos antes de qualquer output.
- Ler do disco apenas em `~/.config/monitoritcd/` ou paths protegidos do dono.

**Pre-commit (bloqueia o commit):**
- `gitleaks detect --no-git -v` em todo arquivo staged.
- `detect-secrets scan --baseline .secrets.baseline`.
- Regex de literais conhecidos (lista expansível em `.pre-commit-config.yaml`):
  - Stripe: `sk_live_`, `sk_test_`, `whsec_`
  - Google: `AIza`, `ya29.`
  - Slack: `xoxb-`, `xoxp-`
  - GitHub: `ghp_`, `gho_`, `ghu_`, `ghs_`, `github_pat_`
  - AWS: `AKIA`, `ASIA`
- Política: literal detectado = commit rejeitado. **Sem `--no-verify`. Sem exceção.**

**CI também valida** — não dá para fugir do pre-commit local.

**Em caso de leak (acidente real):**
1. Revogar a credencial no provedor **imediatamente**.
2. Rotar o secret (gerar novo).
3. Reescrever histórico Git (`git filter-repo`) ou abandonar o repo.
4. Auditar uso da credencial leaked nos últimos 90 dias.
5. Postmortem em `docs/postmortems/`.

📌 Detalhe operacional: **Seção 7 + Seção 13 (Secrets e deployment)**.

---

## 1. Contexto de domínio (3 divisões temáticas)

O sistema cobre **3 áreas correlatas** do direito brasileiro, modeladas como `Topic`:

### 1.1 ITCD (tributário)
- **ITCD = ITCMD = ITD**: tributo estadual sobre heranças e doações.
- Cada UF legisla sua alíquota (2% AM até 8% progressivo RJ/SC/PE).
- Fontes: Assembleias, SEFAZs, DOEs por UF + LexML federal.

### 1.2 Sucessões (Direito Civil — CC arts. 1.784+)
- Herança, testamento, inventário (judicial e extrajudicial), partilha.
- Herdeiros necessários, legítima, deserdação, indignidade.
- União estável, cônjuge supérstite, usufruto vidual.
- Provimento 56/CNJ.
- Fontes: STF, STJ, IBDFAM, Conjur, Migalhas, JOTA.

### 1.3 Regime de Bens (CC arts. 1.639-1.688)
- Comunhão parcial/universal, separação total/obrigatória/convencional.
- Pacto antenupcial, alteração de regime.
- Súmula 377/STF, art. 1.829.
- Aquestos, participação final.
- Fontes: STF, STJ, IBDFAM, doutrina jurídica.

### Fontes federais comuns (tribunais superiores)
- **STF** — RSS oficial; cobre os 3 tópicos.
- **STJ** — RSS oficial; especialmente forte em sucessões e ITCD.
- **TRFs 1-6** — RSS por região (cobertura nacional via federalismo).
- **CNJ** — Provimentos sobre cartórios/inventários extrajudiciais.
- **TJs estaduais** (SP/RJ/MG no MVP) — câmaras de Direito Público (ITCD) e Direito Privado (sucessões).
- **LexML** — base federal consolidada de atos normativos.

### Termos canônicos
Implementados em `filters/keywords.py` separados por tópico:
`KEYWORDS_ITCD`, `KEYWORDS_SUCESSOES`, `KEYWORDS_REGIME_BENS`, `KEYWORDS_DEFAULT` (união).

**Escopo de uso**: dados coletados são todos públicos (atos legislativos, jurisprudência
publicada, notícias) e o consumo é exclusivo do dono. Não há redistribuição. Conteúdo
deve ser preservado **verbatim**, sem alterações automáticas (ver Seção 5).

---

## 2. Arquitetura

```
┌──────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ GitHub Actions   │────▶│ Collectors       │────▶│ Filter (kw+LLM) │
│ (cron 10:13 UTC) │     │ (UFs ativas+fed) │     │ Gemini 2.5 Flash│
└──────────────────┘     └──────────────────┘     └────────┬────────┘
                                                            │
        ┌──────────────────────┐    ┌──────────────────┐    │
        │ Telegram + Email     │◀───│ Notifier         │◀───┤
        │ (com severity tiers) │    │ (sanitizer)      │    │
        └──────────┬───────────┘    └──────────────────┘    │
                   │                                         ▼
                   │                            ┌──────────────────────┐
        ┌──────────▼─────────┐                  │ Firebase             │
        │ Bot interativo     │─────────────────▶│ • Firestore (meta)   │
        │ /comandos do dono  │                  │ • Storage (HTML/PDF) │
        └────────────────────┘                  │ • Audit log          │
                                                └──────────────────────┘
```

- **Headless**: sem frontend web. Interface humana = e-mail + bot Telegram.
- **Stateless por execução**: tudo persiste no Firebase; nada em memória entre runs.
- **Idempotente**: rodar duas vezes no mesmo dia não duplica notificações.
- **Sem backfill**: coleta a partir do go-live. Passado é passado.
- **Defense-in-depth**: sanitização em todas as fronteiras (Seção 7).

---

## 3. Stack técnica

| Camada | Tecnologia | Notas |
|---|---|---|
| Linguagem | Python 3.11+ | Type hints em **todo** código novo. |
| HTTP | `httpx` (async) | NÃO use `requests` síncrono em collectors. |
| HTML parsing | `beautifulsoup4` + `lxml` | Para sites .gov.br com ASP.NET, considerar `selectolax`. |
| HTML sanitization | `bleach` | Antes de armazenar HTML em Storage. |
| RSS | `feedparser` | — |
| PDF | `pypdf` (texto embedado) → `pdfplumber` (layouts) | OCR fora do MVP. |
| Validação | `pydantic` v2 (`SecretStr` p/ secrets) | Modelos em `core/models.py`. |
| Retry | `tenacity` | Backoff exponencial em chamadas externas. |
| LLM primário | Google Gemini 2.5 Flash | 15 RPM, 1.500 req/dia. **Sempre via batch.** |
| LLM fallback | Groq (Llama 3.3) | Quando Gemini estourar cota. |
| Storage metadados | **Firestore** (Firebase Spark) | 1 GB, 50K reads/dia, 20K writes/dia. |
| Storage bruto | **Firebase Storage** | HTML/PDF originais. 5 GB total. |
| Templates | `jinja2` (`autoescape=True`) | E-mails HTML e mensagens Telegram. |
| Bot Telegram | `python-telegram-bot` v21+ | Webhook via Cloud Function. |
| Logging | `structlog` JSON + redator de secrets | Cada log com `source_id`, `uf`, `phase`. |
| Testes | `pytest`, `pytest-recording`, `hypothesis`, `syrupy`, `respx` | Cobertura ≥ 95% (Seção 11). |
| Segurança CI | `bandit`, `pip-audit`, `detect-secrets`, `gitleaks` | Bloqueia merge se HIGH/CRITICAL. |
| Lint/format | `ruff` (lint+format, regras `S` ativas) | Configurar `pyproject.toml`. |
| Tipagem | `mypy --strict` em `core/`, `filters/`, `notifiers/` | Pode relaxar em collectors específicos. |

---

## 4. Decisões tomadas

- ✅ **Storage**: Firebase — Firestore (metadados) + Storage (HTML/PDF) + audit log.
- ✅ **Escopo**: single-user. Hardcode de e-mail/chat_id do dono via env vars.
- ✅ **Backfill**: zero. Coleta a partir do go-live.
- ✅ **WhatsApp**: fase 2. MVP usa Email + Telegram.
- ✅ **LLM não altera dados originais** (Seção 5).
- ✅ **Bot Telegram interativo**: recebe comandos do dono (Seção 8).
- ✅ **Severity tiers**: 🔴 Crítico (push imediato) / 🟠 Alta (digest, destaque) / 🟡 Normal (digest) / 🟢 Baixa (digest semanal).
- ✅ **PDF parsing**: `pypdf` básico no MVP. Sem OCR.
- ✅ **Healthchecks.io**: ping no início e fim de cada execução.
- ✅ **Seleção de UFs ativas**: 27 fontes prontas no repo, ativação gradual via Firestore (Seção 6).
- ✅ **Cobertura de testes**: ≥ 95% (100% em módulos críticos). Inclui segurança, integridade, templates (Seção 11).
- ✅ **Segurança**: defense-in-depth, sanitização em todas as fronteiras, secrets nunca expostos (Seção 7).
- ✅ **MVP enxuto**: 5 estados (SP, RJ, MG, RS, DF) + federais. Demais UFs no repo, desativados.
- ✅ **Fontes em YAML declarativo** (config-driven; classes Python só para casos customizados).
- ✅ **Confirmação em 2 passos** para ações destrutivas no bot (token efêmero 60s, single-use).
- ✅ **Honeytokens** plantados em arquivos do repo (fase 2; alerta imediato em uso).
- ✅ **Rotação de secrets**: lembrete mensal via Telegram (manual; não automação total).
- ✅ **Backup mensal**: GH Action → export Firestore → cifra com `age` → Google Drive (12 retenções).
- ✅ **Retenção**: descartados pelo LLM purgados após 90 dias; `audit_log` 1 ano; `execucoes` 6 meses.
- ✅ **Padrões de pentest aplicados** (Seção 7): validação de `ownerId`, App Check enforce, deploy de functions antes de dados, bloqueio de literais de secret no pre-commit.

---

## 5. Comportamento esperado do LLM (CRÍTICO)

**Princípio inegociável: o LLM NÃO modifica conteúdo original.**

O LLM (Gemini 2.5 Flash, fallback Groq) é usado **apenas** para:

1. **Classificar** o tipo: `PL | Lei Sancionada | Decreto | IN | Portaria | Notícia | Jurisprudência | Doutrina`.
2. **Pontuar** relevância de 0 a 10 → mapeia em severity tier.
3. **Extrair** metadados: UF, número do ato, data, órgão emissor.
4. **Gerar resumo factual** preservando dados originais — nomes, números, datas, cifras **verbatim**.

**O LLM NÃO pode:**

- ❌ Anonimizar nomes ou substituir partes por placeholders (`[Parte]`, etc.).
- ❌ Parafrasear de forma que altere o sentido.
- ❌ Omitir, ofuscar, normalizar ou "limpar" informações.
- ❌ Inferir, especular ou adicionar contexto além do explícito no texto.

### Separação estrita no schema

```
documento/{doc_id}:
  schema_version: 1            # para migrações futuras
  source:
    id, uf, tipo, url
  original:                    # imutável, write-once
    titulo_raw
    texto_raw                  # quando cabe; senão null
    data_publicacao
    fetched_at
    raw_storage_path           # ponteiro pro HTML/PDF em Storage
  llm:                         # gerado por LLM, reprocessável
    classified_at
    llm_model
    llm_prompt_version
    tipo
    relevancia                 # 0-10
    severity_tier              # critico | alta | normal | baixa
    resumo
    metadados_extraidos
    tags
  notificacao:
    enviada, enviada_em, canais
  status: "pending" | "classified" | "notified" | "archived"
```

`original` é **write-once**. Só `llm` e `notificacao` podem ser sobrescritos.

### Reprocessamento

`python -m monitoritcd.main --reprocess --since YYYY-MM-DD [--uf SP]` reclassifica
itens com prompt/modelo novo, preservando `original.*`.

---

## 6. Seleção de UFs ativas (escalonamento gradual)

**Princípio**: o repositório contém YAMLs prontos para todos os 27 entes desde o dia 1.
Ativação é uma **decisão de runtime**, não de código.

### Fonte da verdade: Firestore

Documento único `config/active_states`:

```
config/active_states:
  active_uf: ["SP", "RJ", "MG", "RS", "DF"]   # lista mutável pelo dono
  federal_active: true
  silenced_until:                              # mute temporário (via /silenciar)
    BA: "2026-05-01T00:00:00Z"
  updated_at, updated_by
```

YAML em `config/active_states.default.yaml` é apenas **seed inicial** — copiado pra
Firestore na primeira execução. Daí em diante, Firestore manda.

### Comportamento

- Toda fonte cuja UF não esteja em `active_uf` (ou `silenced_until` no futuro) é
  **pulada silenciosamente**, com log INFO.
- Fontes federais coletam sempre (a menos que `federal_active: false`).
- Adicionar UF é instantâneo: bot `/estados ativar BA` → próxima execução já coleta.
- Toda mudança grava em `audit_log/` com timestamp e comando original.

### Critérios para ativar uma UF

Antes de adicionar à lista:
1. YAML existe em `sources/{UF}/` para ≥ 2 fontes (Assembleia + SEFAZ ou DOE).
2. Cassette VCR em `tests/integration/test_sources_{UF}.py` passa.
3. Pelo menos 1 item real foi classificado em sandbox.
4. Alíquota e regime atual da UF documentados em `docs/ufs/{UF}.md`.

### Comandos de bot

- `/estados listar` — UFs ativas e silenciadas.
- `/estados ativar SP`
- `/estados desativar BA`
- `/silenciar PE 7d` — silencia por 7 dias.

---

## 7. Segurança & Sanitização (CRÍTICO)

**Princípios fundamentais:**

1. **Backend nunca confia em entrada externa** — incluindo a do dono via bot.
2. **Defense in depth** — múltiplas camadas; falha de uma não compromete o sistema.
3. **Dados sensíveis nunca expostos** — em logs, notificações, mensagens de erro, exceções.
4. **Princípio do menor privilégio** — tudo que pode ser restrito, será.
5. **Fail closed** — em dúvida, negar/abortar; nunca permitir.

### Camadas de sanitização

| Origem | Onde sanitizar | Como |
|---|---|---|
| HTML de fontes externas | Antes de salvar em Storage | `bleach.clean(html, tags=ALLOWED, attributes=ALLOWED, strip=True)` |
| Texto extraído | Antes de passar pro LLM | `unicodedata.normalize("NFKC")`, strip de control chars |
| JSON do LLM | Antes de persistir | `pydantic` `extra="forbid"`, validação estrita |
| Comandos do bot | Antes de processar | regex whitelist + pydantic schema por comando |
| Saída p/ Telegram | Antes de enviar | escape Markdown V2 (`\\_\\*\\[\\]\\(\\)\\~\\>\\#\\+\\-\\=\\|\\{\\}\\.\\!`) |
| Saída p/ e-mail | Sempre | Jinja2 `autoescape=True`; CSP no `<head>` |
| URLs em YAML | Na carga | scheme=https, host whitelist (`*.gov.br`, `*.jus.br`, etc.), blocklist IPs internos |
| Logs | Sempre | structlog processor que redige tokens/keys por regex |

### Validação de entrada do bot

Validação em 3 camadas:

1. **Identidade**: `chat_id == TELEGRAM_OWNER_CHAT_ID` exato. Qualquer outro: log + ignora.
2. **Schema**: cada comando tem pydantic model. Argumentos passam por regex whitelist:
   - UF: `^[A-Z]{2}$`
   - Número de ato: `^\d{1,5}/\d{4}$`
   - Período: `^\d{1,3}[dwmy]$` (ex: `7d`, `2w`)
3. **Rate limit**: 10 comandos/minuto (mesmo para o dono — protege contra bot comprometido).

### Gerenciamento de secrets

- **Nunca** em código, YAML, logs ou mensagens de erro.
- `pydantic.SecretStr` para todo campo sensível em `config.py`.
- `__repr__`/`__str__` de modelos de config sobrescritos para mascarar (`"***"`).
- Service account JSON: lido só do env var, parseado em memória, **nunca** persistido em disco.
- Filtro `structlog` redige tokens conhecidos por regex antes de qualquer log sair.
- Mensagens de erro pra o usuário: genéricas (`"falha ao coletar fonte X"`); detalhe vai pro log estruturado.

### Firestore Security Rules

Mesmo single-user, definir em `firestore.rules`:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;   // só admin SDK (service account)
    }
  }
}
```

### SAST e dependências (CI)

`.github/workflows/security.yml` roda em todo PR:

- `bandit -r src/ -ll` — SAST Python (HIGH/MEDIUM bloqueiam merge).
- `ruff check --select S` — regras de segurança ruff.
- `pip-audit` — vulns em deps (HIGH/CRITICAL bloqueiam).
- `safety check` — backup de pip-audit.
- `detect-secrets scan --baseline .secrets.baseline` — secrets vazados.
- `gitleaks detect --source . --no-git -v`.

Pre-commit hook (rápido): `detect-secrets`, `gitleaks`, `ruff`, `bandit -ll`.

### Ameaças mapeadas e mitigações

| Ameaça | Mitigação |
|---|---|
| **SSRF** via URL em YAML de fonte | Whitelist de schemes (https only) + hosts; blocklist RFC1918, link-local, `metadata.google.internal` |
| **XSS** em e-mail HTML | Jinja2 autoescape; CSP `<meta http-equiv="Content-Security-Policy" content="...">` |
| **Markdown injection** no Telegram | Escape de chars especiais antes de enviar |
| **Prompt injection** no LLM | Conteúdo coletado em `<context>...</context>`; instruções em system prompt; output validado por pydantic com `extra="forbid"` |
| **NoSQL injection** em Firestore | Pydantic; nunca string concat; valores via parâmetros |
| **Shell injection** | Não usar `shell=True`; sempre `list[str]` em `subprocess` |
| **Path traversal** em `raw_storage_path` | `pathlib.PurePosixPath`; reject `..` e absolute paths |
| **Vazamento em log** | structlog redactor processor com regex de tokens |
| **DoS via fonte lenta** | Timeout 30s + concorrência limitada por host |
| **Pickle deserialization** | Proibido. Apenas JSON via pydantic. |

### Padrões adicionais (pentest 2026-04-20 + standards herdados)

**Input limits obrigatórios** (princípio "backend nunca confia no frontend" — framework GSD):
- Todo input do bot/webhook tem `MAX_LENGTH` (string), `MAX_ITEMS` (lista), `MAX_DEPTH` (objeto aninhado) explícito.
- Pydantic `Field(max_length=N, max_items=N)` obrigatório em todo campo de entrada.
- Payload acima do limite: **rejeitar** (não truncar silenciosamente). Resposta genérica ao cliente; log estruturado completo no backend.
- Limites são definidos no backend **independente** do que o cliente envia.
- Política aplica a todo endpoint: webhook Telegram, Cloud Functions, comandos do bot, parsers de YAML.

**Variáveis de ambiente e secrets NUNCA no código fonte**:
- Pre-commit hook bloqueia literais conhecidos por regex (commit rejeitado, sem exceção):
  - `sk_live_`, `sk_test_`, `whsec_` (Stripe)
  - `AIza...` (Google API), `ya29.` (OAuth tokens)
  - `xoxb-`, `xoxp-` (Slack)
  - `ghp_`, `gho_`, `ghu_`, `ghs_`, `github_pat_` (GitHub)
  - Padrões adicionais conforme integrações forem adicionadas.
- `gitleaks` + `detect-secrets` no pre-commit e no CI.
- `.secrets.baseline` versionado; review obrigatório em PR que altere o baseline.
- Regra: **API key detectada = commit rejeitado**. Sem `--no-verify`.

**Validação de `ownerId`** (defense-in-depth):
- Mesmo single-user, toda operação Firestore valida `owner_id` ANTES de ler/escrever.
- Razão: se o service account vazar para outro projeto Firebase, blast radius fica contido — docs com owner errado são rejeitados.
- Implementação:
  - Campo `owner_id` em todo doc raiz.
  - Helper `assert_owner(doc)` antes de qualquer mutation.
  - Queries sempre incluem `where("owner_id", "==", OWNER_ID)`.

**Firebase App Check enforce**:
- App Check ativo no Firestore E Storage.
- Bloqueia acesso de clientes não-atestados (mesmo com chave SDK exposta acidentalmente).
- CI/scripts admin: usam service account (bypassa App Check legitimamente).
- Webhook do bot (Cloud Function): atesta via token de sessão.

**Padrões herdados não aplicáveis hoje** (mantidos como referência caso o sistema evolua):
- ⚪ **Email verify obrigatório** — N/A: owner é fixo via env var.
- ⚪ **MFA grace 7d** — N/A: não há login de usuário.
- ⚪ **Anti trial-farming** — N/A: não há trial/cadastro.

Se o sistema futuramente expandir para múltiplos usuários, **estes padrões viram obrigatórios** sem discussão.

**Ordem de deploy (contas protegidas)**:
- Cloud Functions (validação, triggers Firestore) DEVEM ser deployadas **antes** de qualquer migração ou seed de dados.
- Razão: dados escritos antes dos triggers existirem passam sem validação — corrupção silenciosa.
- `firestore.rules` também deployadas antes — **sempre** antes.
- Pipeline CI gated, com cada etapa como dependência hard da seguinte:
  ```
  deploy_rules → deploy_functions → seed_data → run_migrations
  ```

### Auditoria

Toda ação do bot, mudança de config e exceção crítica grava em `audit_log/`:

```
audit_log/{timestamp}:
  actor: "bot:OWNER" | "system:cron"
  action: "states.activate" | "config.update" | "doc.notify" | ...
  payload: { ... }
  result: "success" | "failure"
  error: "..." (sanitizado)
```

---

## 8. Bot Telegram interativo

### Comandos suportados (MVP)

| Comando | Função |
|---|---|
| `/start` | Saudação + lista comandos |
| `/status` | Última coleta, fontes ativas/falhando, cota LLM restante |
| `/buscar <termo> [UF] [ano]` | Busca em `documento/` por título/resumo |
| `/observar <termo>` | Adiciona à watch list (alerta imediato em match futuro) |
| `/observar listar` | Lista watches ativos |
| `/observar remover <id>` | Remove watch |
| `/marcar <doc_id> <tag>` | Tag pessoal num doc |
| `/silenciar <UF> <duração>` | Mute temporário |
| `/estados listar` / `ativar` / `desativar` | Gerencia UFs ativas |
| `/relatorio [diario\|semanal]` | Digest sob demanda |

### Arquitetura

- Telegram → webhook → Cloud Function (Firebase) → handler Python.
- Cloud Function valida `chat_id`, parseia comando, atualiza Firestore.
- Resposta enviada via Bot API.
- **Não use polling** — webhook é mais barato e mais rápido.

---

## 9. Estrutura de diretórios (proposta)

```
MonitorITCD/
├── .github/workflows/
│   ├── monitor.yml              # cron diário
│   ├── security.yml             # SAST, deps, secrets
│   └── tests.yml                # pytest, coverage, mutation
├── src/monitoritcd/
│   ├── core/
│   │   ├── base_collector.py
│   │   ├── models.py            # pydantic models
│   │   ├── config.py            # SecretStr, validação env
│   │   └── sanitize.py          # wrappers de sanitização
│   ├── collectors/
│   │   ├── generic_rss.py
│   │   ├── generic_html.py
│   │   ├── lexml.py
│   │   └── custom/
│   ├── filters/
│   │   ├── keywords.py
│   │   ├── prescore.py
│   │   └── llm_classifier.py
│   ├── storage/
│   │   ├── firestore_store.py
│   │   ├── firebase_storage.py
│   │   └── audit_log.py
│   ├── notifiers/
│   │   ├── email_notifier.py
│   │   ├── telegram_notifier.py
│   │   ├── severity.py          # mapeamento relevancia → tier → canal
│   │   └── templates/
│   │       ├── email.html.j2
│   │       └── telegram.md.j2
│   ├── bot/
│   │   ├── handlers.py          # comandos
│   │   ├── auth.py              # validação chat_id + rate limit
│   │   └── webhook.py           # entry point Cloud Function
│   ├── security/
│   │   ├── url_validator.py     # anti-SSRF
│   │   ├── log_redactor.py      # structlog processor
│   │   └── markdown_escape.py
│   ├── dedup.py
│   └── main.py
├── sources/                     # YAML para TODAS as 27 UFs (mesmo desativadas)
│   ├── _federal/
│   ├── AC/, AL/, AP/, AM/, BA/, CE/, DF/, ES/, GO/, MA/, MT/, MS/, MG/,
│   ├── PA/, PB/, PR/, PE/, PI/, RJ/, RN/, RS/, RO/, RR/, SC/, SP/, SE/, TO/
├── config/
│   ├── active_states.default.yaml   # seed inicial; runtime usa Firestore
│   └── allowed_hosts.yaml           # whitelist anti-SSRF
├── docs/
│   └── ufs/{UF}.md              # alíquota, regime, peculiaridades
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   │   ├── sanitization/
│   │   ├── input_validation/
│   │   ├── ssrf/
│   │   └── prompt_injection/
│   ├── templates/               # snapshot tests
│   ├── e2e/
│   └── cassettes/               # VCR
├── firestore.rules
├── pyproject.toml
├── .pre-commit-config.yaml
├── .secrets.baseline
├── .env.example
└── README.md
```

---

## 10. Convenções de código

### Estilo
- Comentários e docstrings em **PT-BR**. Nomes em **inglês** (exceto termos jurídicos: `causa_mortis`, `espolio`).
- Type hints obrigatórios em toda função pública. `mypy --strict` em `core/`, `filters/`, `notifiers/`, `security/`.
- **Async first** em collectors e bot. Nada de `requests` síncrono.
- Pydantic em toda fronteira de processo (HTTP, DB, LLM, env, bot).

### Erros e logging
- `structlog` JSON. Cada log com `source_id`, `uf`, `phase`, `correlation_id`.
- Nunca `except: pass`. Nunca `except Exception` sem re-raise ou log.
- Falha em uma fonte **não pode** derrubar a execução. Cada collector roda isolado.
- `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential())`.
- **Mensagens de erro pro usuário são genéricas**; detalhe técnico vai pro log.

### Comentários
- Comente o **porquê**, nunca o **o quê**.
- Decisões de domínio ("MA tem alíquota progressiva, requer parsing especial") **devem** virar comentário.

### Performance
- `asyncio.gather` para collectors do mesmo nível.
- Rate limit: ≥ 2s entre requisições ao mesmo domínio (`asyncio.Semaphore` por host).
- Timeouts: 30s/req.

---

## 11. Estratégia de testes (cobertura completa)

**Premissa**: testes automatizados em **toda a superfície do sistema** — segurança, integridade,
templates (UI), fluxos. CI bloqueia merge se cobertura < 95% global ou < 100% em módulos críticos,
ou se qualquer teste de segurança falhar.

### Pirâmide

```
       /\
      /e2\         e2e (~5%): fluxo completo com Firebase emulator
     /----\
    /integ \       integração (~25%): collectors+filters+storage com VCR
   /--------\
  /  unit    \     unitários (~70%): cada módulo isolado
 /____________\
```

### Tipos de teste obrigatórios

| Tipo | Diretório | Ferramenta | Cobertura |
|---|---|---|---|
| Unitários | `tests/unit/` | pytest | 100% em `core/`, `filters/`, `dedup.py`, `notifiers/`, `security/` |
| Integração | `tests/integration/` | pytest + `pytest-recording` (VCR) | 95% em `collectors/` |
| Sanitização | `tests/security/sanitization/` | pytest | 100% nas camadas da Seção 7 |
| Validação de entrada | `tests/security/input_validation/` | pytest + `hypothesis` (fuzz) | 100% em parsers de bot |
| SSRF | `tests/security/ssrf/` | pytest | 100% em `url_validator` |
| Prompt injection | `tests/security/prompt_injection/` | pytest + cassettes | Conteúdo malicioso → output ainda válido |
| Templates (UI) | `tests/templates/` | pytest + `syrupy` (snapshots) | 100% em `notifiers/templates/` |
| E2E | `tests/e2e/` | pytest + Firebase emulator | Fluxos críticos do MVP |
| Mutation | n/a (CI weekly) | `mutmut` | ≥ 80% killed em `filters/`, `dedup.py`, `security/` |
| SAST | CI sempre | `bandit`, `ruff -S` | Zero issues HIGH/MEDIUM |
| Dep audit | CI sempre | `pip-audit`, `safety` | Zero HIGH/CRITICAL |
| Secret scan | pre-commit + CI | `detect-secrets`, `gitleaks` | Zero detections |

### Testes de templates (a "UI" do sistema)

Headless ≠ sem UI: e-mail e Telegram **são** UI.

- **Snapshot tests** com `syrupy` — qualquer mudança em template precisa aprovação explícita.
- **HTML compliance**: validar com `html5lib`; CSS inline para Gmail (`premailer`).
- **Telegram**: testar split de msgs > 4096, escape de chars especiais, formatação de severity.
- **Edge cases**: corpo vazio, 1000 itens, caracteres especiais, emojis, RTL.

### Testes de segurança específicos

- **Fuzz nos comandos do bot** (`hypothesis`): nenhum input aleatório derruba handler.
- **Property tests** no wrapper de `bleach`: garantir que nenhum HTML malicioso passa.
- **SSRF**: tentar `http://localhost`, `http://169.254.169.254`, `file://`, IPv6 link-local.
- **Prompt injection**: conteúdo "Ignore previous instructions..." → output JSON válido com schema.
- **Markdown injection**: input com `*`, `_`, `[` → escapado corretamente no Telegram.
- **Path traversal**: `../../../etc/passwd` em qualquer campo de path → rejeitado.

### Cobertura

- **Branch coverage** (não só line): `pytest --cov --cov-branch`.
- **Mutation testing** semanal em módulos críticos. Gate: ≥ 80% killed.
- Limites em `pyproject.toml`:
  ```toml
  [tool.coverage.report]
  fail_under = 95
  exclude_lines = ["pragma: no cover", "raise NotImplementedError"]
  ```

### Gate de pré-commit / CI

```bash
ruff check . && \
ruff format --check . && \
mypy src/monitoritcd/{core,filters,notifiers,security} && \
bandit -r src/ -ll && \
detect-secrets scan --baseline .secrets.baseline && \
pytest tests/security/ -v && \
pytest --cov=src/monitoritcd --cov-branch --cov-report=term-missing --cov-fail-under=95
```

### Ambiente de teste

- **Firebase emulator** (`firebase-tools`) para integração com Firestore/Storage sem custo.
- **`respx`** para mockar `httpx`.
- **`pytest-recording`** para HTTP real (gravado uma vez).
- LLM em testes: cassettes; **nunca** API real em CI por padrão.

---

## 12. Adicionar uma fonte nova (workflow)

1. Criar `sources/{UF}/{tipo}.yaml` (validação pydantic na carga).
2. Layout HTML padrão → `parser: generic_html` + selectors CSS.
3. RSS → `parser: generic_rss`.
4. Lógica especial → `collectors/custom/{uf}_{nome}.py`.
5. Cassette VCR em `tests/integration/test_sources_{UF}.py`.
6. `python -m monitoritcd.main --sources {UF}/{tipo} --dry-run`.
7. Commit + PR (CI roda toda a bateria de testes).
8. Para **ativar** o monitoramento: `/estados ativar {UF}` no bot.

---

## 13. Secrets e deployment

GitHub Secrets:

| Secret | Uso |
|---|---|
| `GEMINI_API_KEY` | LLM primário |
| `GROQ_API_KEY` | LLM fallback |
| `RESEND_API_KEY` | API key do Resend (e-mail de envio) |
| `RESEND_FROM_EMAIL` | Endereço do domínio verificado no Resend (remetente exibido como "SefWorkStation") |
| `EMAIL_RECIPIENT` | E-mail do dono |
| `TELEGRAM_BOT_TOKEN` | Bot do BotFather |
| `TELEGRAM_OWNER_CHAT_ID` | Chat ID do dono (ÚNICO autorizado) |
| `TELEGRAM_WEBHOOK_SECRET` | Token X-Telegram-Bot-Api-Secret-Token |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | JSON do SA, inteiro como string |
| `FIREBASE_PROJECT_ID` | ID do projeto |
| `FIREBASE_STORAGE_BUCKET` | `{project}.appspot.com` |
| `HEALTHCHECKS_URL` | Ping de dead-man's-switch |

**Nunca commitar:** `.env`, `*.json` de SA, snapshots com dados sensíveis, `.secrets.baseline` exceto após review.

`.gitignore`: `.env`, `*.db`, `*.sqlite*`, `firebase-*.json`, `.venv/`, `__pycache__/`, `*.pyc`, `.coverage`, `htmlcov/`, `.mutmut-cache`.

---

## 14. Cron e janela de execução

- Workflow: **`13 10 * * *`** (10:13 UTC = 07:13 BRT) — fora dos horários "redondos".
- `workflow_dispatch` para execução manual com inputs (ex: `--reprocess`, `--source-id`).
- Timeout: **30 minutos**. Se passar, há algo errado.

---

## 15. Armadilhas conhecidas

- **GH Actions runners US-based**: alguns sites .gov.br bloqueiam. Diagnóstico: 403/timeout em cron + sucesso local. **Solução implementada (2026-04-25)**: campo `geo_restricted: true` no YAML da fonte. Em ConnectTimeout/ConnectError direto, `BaseCollector.fetch()` faz fallback automático para Cloud Function `proxy_br` em região `southamerica-east1` (deploy via `.github/workflows/deploy-functions.yml`). A Cloud Function valida whitelist (`.gov.br`, `.jus.br`, `.leg.br`) + auth via `X-Proxy-Token`. **Reserva técnica**: worker local Windows (`scripts/install_local_monitor_task.ps1`) roda `--only-geo-restricted` diariamente quando proxy não disponível.
- **ASP.NET com VIEWSTATE**: muitos portais legislativos. Pode exigir Playwright (pesado) ou parsing manual do form.
- **`feedparser` engasga em RSS mal-formado**: try/except e fallback para HTML scraping.
- **Gemini retorna JSON malformado** em ~3%: `response_mime_type="application/json"` + try/except + retry.
- **Firestore reads N+1**: cuidado com loops; use `get_all()` em batch.
- **Telegram 4096 chars/msg**: dividir antes de enviar.
- **Fuso BRT vs UTC**: tudo em UTC; converter só na renderização.
- **DOEs em PDF escaneado**: marcar `requires_manual_review` e notificar dono.
- **Firebase Storage sem CDN no Spark**: download recente conta na cota; baixe sob demanda.
- **Cloud Function cold start**: bot pode demorar 2-5s na primeira chamada do dia.

---

## 16. Critérios de "pronto"

Um collector está pronto quando:
- [ ] YAML em `sources/{UF}/`
- [ ] `--dry-run` funciona
- [ ] Cassette VCR em `tests/integration/`
- [ ] Pelo menos 1 item real classificado em sandbox
- [ ] `docs/ufs/{UF}.md` atualizado

O sistema está pronto para deploy quando:
- [ ] 5 estados (SP, RJ, MG, RS, DF) + federais funcionando
- [ ] Cobertura de testes ≥ 95% global, 100% em críticos, 0 falhas em segurança
- [ ] CI verde em SAST, deps, secrets
- [ ] E-mail e Telegram entregando ao dono
- [ ] Bot respondendo a comandos básicos
- [ ] Workflow rodando 3 dias seguidos no cron sem falhas
- [ ] Healthchecks.io configurado e pingando
- [ ] README com setup completo
- [ ] `firestore.rules` com `deny all` aplicado

---

## 17. Referências

- `prompt-itcd-monitor.md` (Drive): especificação original do produto.
- Tabela das 27 UFs: a ser construída em `README.md`.
- `docs/ufs/{UF}.md`: peculiaridades por estado.
