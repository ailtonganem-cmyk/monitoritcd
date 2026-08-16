# 70 — Testes e validação: gates objetivos e prova empírica

> Fonte da verdade da etapa **V** do PREVC (`10`). Gate vermelho = tarefa não
> concluída. Proibido skip, baseline novo, threshold rebaixado ou supressão que
> oculte falha.

## Gates objetivos

```bash
ruff check .                                   # lint (regras S de segurança ativas)
ruff format --check .                          # formatação
mypy src/monitoritcd/{core,filters,notifiers,security}   # tipos (strict)
bandit -r src/ -ll                             # SAST — HIGH/MEDIUM bloqueiam
detect-secrets scan --baseline .secrets.baseline
pytest tests/security/ -v                      # segurança primeiro: falhou, para aqui
pytest --cov=src/monitoritcd --cov-branch --cov-report=term-missing --cov-fail-under=95
```

Rodar **todos os aplicáveis à mudança** e relatar a **saída literal**, não a
conclusão. Suíte focal primeiro (a spec da mudança), suíte ampla depois — o
feedback rápido pega o erro onde ele nasceu.

**Limiares vigentes** (`pyproject.toml`): cobertura **branch ≥ 95 %** global,
**100 %** em `core/`, `filters/`, `dedup.py`, `notifiers/`, `security/`;
mutation ≥ 80 % killed em `filters/`, `dedup.py`, `security/` (`mutmut`, semanal
no CI); zero achado HIGH/CRITICAL em `pip-audit`; zero detecção de secret.

## Prova por mutação (correção de defeito)

Correção de bug exige teste que **prove** a correção: reverta a correção → o
teste **reprova**; restaure → **passa**. Teste que passa nos dois estados não
prova nada — relate-o como falho em vez de entregá-lo.

## Tipos de teste obrigatórios

| Tipo | Diretório | Ferramenta |
| --- | --- | --- |
| Unitários | `tests/unit/` | pytest |
| Integração de fontes | `tests/integration/` | pytest + `pytest-recording` (cassette VCR) |
| Sanitização | `tests/security/sanitization/` | pytest — 100 % das camadas do `60` |
| Validação de entrada | `tests/security/input_validation/` | pytest + `hypothesis` (fuzz do bot) |
| SSRF | `tests/security/ssrf/` | pytest — `localhost`, `169.254.169.254`, `file://`, IPv6 link-local |
| Prompt injection | `tests/security/prompt_injection/` | pytest + cassettes — conteúdo malicioso ainda produz JSON válido |
| Templates (a UI — `50`) | `tests/templates/` | pytest + `syrupy` (snapshot) |
| E2E | `tests/e2e/` | pytest + emulador Firebase |

- **LLM em teste: sempre cassette.** Nunca API real no CI por padrão.
- `respx` para mockar `httpx`; emulador Firebase para Firestore/Storage.
- Fluxo crítico do domínio (`40`) tem teste de integração, não só unitário.

## Julgamento de qualidade (além dos gates)

- **Saídas visíveis** (`50`): conferir o e-mail e a mensagem do Telegram
  renderizados — não só o snapshot que passou. Emoji de tier, escape, split.
- **Coleta:** `python -m monitoritcd.main --sources {UF}/{tipo} --dry-run` com
  dados reais da fonte antes de dar a fonte por pronta.
- **Dados:** conferir o documento gravado no Firestore — campo `original`
  intacto, `contexto` rotulado, `severity_tier` coerente com a relevância.

## Armadilhas conhecidas — não pagar duas vezes

- **`--dry-run` usa `InMemoryStorage` sem seed** → não há `config/active_states`
  → **nenhuma UF estadual é coletada, só as federais.** Smoke com `--dry-run`
  jamais prova que a coleta de MG funciona.
- **`pip install -e` aponta para outro worktree.** O pacote instalado em modo
  editável resolve para o `src/` de onde foi instalado. Em worktree, ou recriar
  o `.venv` (`80`), ou rodar com `PYTHONPATH=src`. `.venv` **nunca** é
  symlinkado entre worktrees — um `pip install` contamina todos.
- **Runner do GitHub Actions é US-based**; portais `.gov.br` bloqueiam. Sintoma:
  403/timeout no cron + sucesso local. Tratamento: `geo_restricted: true` no
  YAML → fallback automático para a Cloud Function `proxy_br`
  (`southamerica-east1`, allowlist `.gov.br`/`.jus.br`/`.leg.br`, auth por
  `X-Proxy-Token`) — ADR-0005. Reserva: worker local Windows
  (`scripts/install_local_monitor_task.ps1`) com `--only-geo-restricted`.
- **ASP.NET com VIEWSTATE** em portais legislativos: exige parsing manual do
  form (ou Playwright, pesado — última opção).
- **`feedparser` engasga em RSS malformado**: try/except + fallback para scraping.
- **Gemini devolve JSON malformado em ~3 %**: `response_mime_type="application/json"`
  + retry; a validação pydantic é a rede final.
- **Telegram corta em 4096 caracteres**; **Firestore sofre N+1** em laço;
  **Storage no Spark não tem CDN** (download conta na cota); **cold start** de
  function chega a 5 s.
- **Fuso**: tudo em UTC no armazenamento; BRT só na renderização.
- **Mudança em `src/` que afeta o bot exige redeploy** da function `bot_webhook`
  (ela instala o pacote do branch principal, não do working tree).

Armadilha nova descoberta = uma linha aqui, no mesmo trabalho.
