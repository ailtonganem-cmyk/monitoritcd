# Painel, cadeia de IA e HML — plano e segurança

Data: 2026-09-13. HML = localhost. Sem Functions, Rules, IAM ou domínio próprio.

## Diagnóstico HML (por que não funcionava)

| Fato | Efeito |
|---|---|
| Processo `python -m monitoritcd.main painel` **não estava escutando** `127.0.0.1:8765` | Angular/`ng serve` na `:4200` chama `/api/*` no próprio Vite e recebe 404 |
| Cookie `SameSite=Strict` na origem 8765 | Mesmo com API no ar, o browser na `:4200` **não** envia a sessão |
| `GOOGLE_OAUTH_CLIENT_ID` ausente no `.env` | GIS não inicializa; tela de login vazia |
| Emuladores Firestore/Storage **não** estavam no ar | Coleta real (não dry-run) não grava metadados locais |

Caminho HML canônico: **uma origem** `http://127.0.0.1:8765` (Python serve o `dist` Angular). `ng serve` só com `proxy.conf.json` apontando `/api` para 8765.

## Integração de IA que faltava

O painel gravava `config/painel/ia-provedores.json` (ordem, modelo, esforço, ligado/desligado). `_make_backends` **ignorava** esse arquivo e sempre montava Gemini → Groq.

Plano (implementado neste recorte):

1. Ler a cadeia do JSON do painel (só metadado).
2. Instanciar provedor **só** se a família estiver ligada **e** a chave existir no ambiente (nunca no JSON, nunca na API).
3. Tentar em ordem; 429/5xx de quota → próximo; todos esgotados → `LLMProvidersExhaustedError` (pipeline defere, não inventa classificação).
4. Famílias sem adaptador ou sem chave → puladas com log, sem secret.
5. Ollama só em `127.0.0.1` / `::1`.
6. `dry-run` continua FakeLLM (zero rede).

Chaves previstas (todas opcionais, `.env` / GitHub Secrets):

| Família | Variável |
|---|---|
| google | `GEMINI_API_KEY` (já existe) |
| groq | `GROQ_API_KEY` (já existe) |
| openai | `OPENAI_API_KEY` |
| anthropic | `ANTHROPIC_API_KEY` |
| xai | `XAI_API_KEY` |
| ollama | sem chave; `OLLAMA_BASE_URL` default `http://127.0.0.1:11434` |

## Planejamento de segurança

1. **Authn** — Google ID token (`aud` = client_id, e-mail verificado). Allowlist rígida `ailtonganem@gmail.com`. Outro e-mail → 403.
2. **HML sem OAuth client** — `POST /api/auth/hml` só se `Host` é loopback **e** `ENV != production`. Emite a mesma sessão do founder. Não aceita e-mail arbitrário. Desligado em produção.
3. **Sessão** — cookie HMAC HttpOnly, SameSite=Lax, Path=/, TTL 12 h. Sem JWT no localStorage.
4. **Bind** — servidor do painel em `127.0.0.1` (não 0.0.0.0).
5. **Segredos** — proibidos em git, JSON do painel, HTML, logs e respostas `/api/ia` (só id/família/modelo/esforço/habilitado).
6. **Fontes** — URL anti-SSRF na inclusão; exclusão só de `sources/_operador/`.
7. **IA** — provedor desligado não gera tráfego; texto original permanece verbatim; timeout já nos provedores.
8. **Fora** — sem alterar Functions, Rules, IAM; sem deploy; sem domínio próprio.

## Como subir HML

```bash
# 1) emuladores (Firestore/Storage)
firebase emulators:start --project demo-monitoritcd --only firestore,storage,ui

# 2) painel (API + Angular dist)
python -m monitoritcd.main painel
# http://127.0.0.1:8765
```

Rebuild do front: `cd apps/painel && npx ng build`.
