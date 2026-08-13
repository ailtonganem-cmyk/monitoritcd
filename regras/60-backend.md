# 60 — Backend: segurança server-side, limites, secrets, integrações

> Fonte da verdade do **backend**. Os três princípios canônicos do projeto vivem
> aqui: nunca confiar na entrada, `input_limits` obrigatórios e secrets fora do
> código. Modelagem formal de ameaças: `docs/THREAT_MODEL.md` (STRIDE) e
> `SECURITY.md`.

## Princípio 1 — Nunca confiar na entrada

Backend valida tudo, sempre. **Cliente é hostil por padrão**, e "cliente" inclui:

- o **bot Telegram** (mesmo com `chat_id` correto — o token pode estar comprometido);
- **webhooks externos** (assinatura conferida antes de qualquer parsing);
- **conteúdo coletado** (HTML, PDF e RSS são entrada não confiável);
- a **configuração YAML** das fontes (validada por pydantic; URL por whitelist);
- **o próprio dono** operando o sistema.

Regras de implementação:

- Validação dupla — no recebimento **e** antes de persistir.
- Nenhuma decisão de autoridade tomada no cliente.
- Rate limiting em toda superfície, inclusive as "internas".
- **Timeout obrigatório** em toda chamada externa (30 s/request).
- Erro genérico para a superfície; detalhe técnico só no log estruturado.
- Sem exceção "porque é só pra mim".

## Princípio 2 — `input_limits` obrigatórios

Toda entrada tem limite explícito no backend. **Excedeu = rejeita** — nunca
trunca em silêncio.

| Limite | Aplicação | Exemplos vigentes |
| --- | --- | --- |
| `MAX_LENGTH` | strings | título ≤ 500, comando do bot ≤ 256, URL ≤ 2048 |
| `MAX_ITEMS` | listas | tags por documento ≤ 20, watches ≤ 100 |
| `MAX_DEPTH` | objetos aninhados | JSON do LLM ≤ 5 níveis, YAML de config ≤ 6 |
| `MAX_BYTES` | payloads | HTML ≤ 5 MB, PDF ≤ 20 MB, request body ≤ 1 MB |
| `MAX_DURATION` | timeouts | HTTP 30 s, LLM 60 s, function 540 s |

- `pydantic.Field(max_length=…, max_items=…)` em **todo** modelo de entrada.
- Validação no boundary (HTTP → modelo); falha = 400 / log + abort.
- Limites centralizados em `core/limits.py` e importados — nunca redigitados.
- Limites são **propriedade do backend**: não derivam do que o cliente envia.

## Princípio 3 — Secrets: proibidos em código fonte

**Nenhum** secret, token, senha ou credencial em arquivo versionado. Nunca, sem
exceção, sem `--no-verify`.

| Local | Permitido? |
| --- | --- |
| GitHub Secrets | ✅ única fonte para produção |
| `.env` local (gitignored) | ✅ apenas dev |
| Secret Manager / config de Functions | ✅ |
| `.py`, `.yaml`, `.json`, `.md` — inclusive "test", "example", "fixture" | ❌ |
| Comentário, docstring, log, mensagem de erro, e-mail, mensagem do bot | ❌ |

- Sempre `pydantic.SecretStr`, `os.environ[...]` ou loader explícito.
- `__repr__`/`__str__` de modelos de config mascaram (`"***"`).
- Processor do `structlog` **redige tokens conhecidos** antes de qualquer saída.
- Service account: lido do env var, parseado em memória, **nunca** gravado em disco.
- Pre-commit e CI bloqueiam por regex de literais conhecidos (Stripe, Google
  `AIza`/`ya29.`, Slack, GitHub `ghp_`…, AWS `AKIA`/`ASIA`) + `gitleaks` +
  `detect-secrets`. Detecção = commit rejeitado.
- **Em caso de leak real:** revogar no provedor → rotar → reescrever histórico
  (`git filter-repo`) ou abandonar o repo → auditar uso nos últimos 90 dias →
  postmortem em `docs/` (modelo: `docs/templates/postmortem.md`).

## Camadas de sanitização (defense in depth)

| Origem | Onde | Como |
| --- | --- | --- |
| HTML de fonte externa | antes de salvar no Storage | `bleach.clean(..., strip=True)` com allowlist |
| Texto extraído | antes de ir ao LLM | `unicodedata.normalize("NFKC")` + strip de control chars |
| JSON do LLM | antes de persistir | pydantic com `extra="forbid"` |
| Comando do bot | antes de processar | regex allowlist + modelo pydantic por comando |
| Saída Telegram | antes de enviar | escape MarkdownV2 (`50`) |
| Saída e-mail | sempre | Jinja2 `autoescape=True` + CSP |
| URL em YAML | na carga | `https` only + allowlist de host + blocklist de IP interno |
| Logs | sempre | redator de tokens por regex |

## Validação da entrada do bot — 3 camadas

1. **Identidade:** `chat_id == TELEGRAM_OWNER_CHAT_ID` exato; qualquer outro:
   log + ignora (nunca responde — não confirma existência do bot).
2. **Schema:** modelo pydantic por comando; argumentos por regex allowlist —
   UF `^[A-Z]{2}$`, ato `^\d{1,5}/\d{4}$`, período `^\d{1,3}[dwmy]$`.
3. **Rate limit:** 10 comandos/minuto — **inclusive para o dono** (protege
   contra bot comprometido).

Webhook: `X-Telegram-Bot-Api-Secret-Token` conferido antes de qualquer parsing.

## Ameaças de implementação obrigatórias

SSRF (allowlist de scheme/host + blocklist RFC1918, link-local e
`metadata.google.internal`) · XSS em e-mail · markdown injection no Telegram ·
prompt injection (`40`) · injeção em query Firestore (nunca concatenar string) ·
shell injection (nunca `shell=True`; sempre `list[str]`) · path traversal em
`raw_storage_path` (`PurePosixPath`, rejeitar `..` e caminho absoluto) ·
vazamento em log · DoS por fonte lenta (timeout + concorrência limitada por
host) · desserialização (pickle **proibido**; só JSON via pydantic).

## Persistência

- **Firestore Rules:** `allow read, write: if false` — acesso só pelo Admin SDK
  com service account. Storage idem.
- **`assert_owner` antes de toda mutation** e `where("owner_id", "==", OWNER_ID)`
  em toda query. Mesmo single-user: se a service account vazar para outro
  projeto, o blast radius fica contido.
- **App Check** ativo em Firestore e Storage.
- **`original` é write-once** (`40`) — nenhuma rotina reescreve conteúdo coletado.
- **`audit_log`**: toda ação do bot, mudança de config e exceção crítica grava
  `actor`, `action`, `payload`, `result`, `error` (sanitizado), encadeados por
  hash (ADR-0004).
- Cuidado com N+1: usar `get_all()` em lote, nunca `get()` dentro de laço.

## Erros e logging

- `structlog` JSON; todo log com `source_id`, `uf`, `phase`, `correlation_id`.
- Nunca `except: pass`; nunca `except Exception` sem re-raise ou log.
- **Falha em uma fonte não pode derrubar a execução** — cada collector roda
  isolado; `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential())`.
- Concorrência: `asyncio.gather` por nível, `Semaphore` por host, ≥ 2 s entre
  requisições ao mesmo domínio.
- Tudo em UTC; converter para BRT só na renderização (`50`).

## Operações em dados e deploy

- **Ordem de deploy é gate duro:** `firestore.rules` → Cloud Functions → seed →
  migrações. Dado escrito antes dos triggers existirem passa sem validação —
  corrupção silenciosa.
- Deploy de function **sempre com escopo explícito**
  (`firebase deploy --only functions:<nome>`) — deploy amplo apaga o que não
  está no código local.
- Escrita em massa fora do fluxo normal (backfill, migração, correção):
  `--dry-run` primeiro, **e consulta prévia ao dono** (deploy de código ≠
  escrita de dados). Delete em massa: nunca sem ordem expressa (`90`).
- Script administrativo trava o projeto alvo (assert do `project_id`) antes de
  executar.
