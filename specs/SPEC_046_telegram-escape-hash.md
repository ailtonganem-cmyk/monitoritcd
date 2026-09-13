# SPEC 046 — Telegram 400: `#` vindo de entidade HTML no digest

## Identificação

- **ID / slug:** `046` · `telegram-escape-hash`
- **Porte:** trivial / focal (`regras/10-metodo-trabalho.md`)
- **Issue:** https://github.com/ailtonganem-cmyk/monitoritcd/issues/46
- **Worktree:** worktree Orca atual (`telegram-rejeita-digest-com-400-caractere-n-o-es`)
- **Orquestrador:** Grok 4.6
- **Executor previsto:** simples — fatia local, implementada na sessão do orquestrador (TRACK_A; split_gate AER)
- **MCPs/CLIs a utilizar:** GitHub (leitura da issue/run); pytest local. Sem Firebase, sem deploy.

## Problema e objetivo

O digest Telegram (run [29856542796](https://github.com/ailtonganem-cmyk/monitoritcd/actions/runs/29856542796)) recebeu 400 `Character '#' is reserved and must be escaped with the preceding '\'` num chunk MarkdownV2. A entrega ocorreu via fallback plain-text (perda de formatação). Objetivo: o render MarkdownV2 não introduz `#` nu, inclusive quando o documento tem aspas.

## Escopo

- **Dentro:** desligar autoescape HTML em templates Markdown (`telegram.md.j2`, `digest.md.j2`); manter autoescape HTML nos e-mails; teste de mutação com `"` / `'` / `#` / `&` na URL.
- **Fora:** remover o fallback plain-text; alterar `escape_markdown_v2`; redeploy de function; fechar a issue no GitHub (orquestrador após merge); código morto `_escape_for_template`.

## Mapa de arquivos

| Arquivo | O que muda |
| --- | --- |
| `src/monitoritcd/notifiers/email_notifier.py` | `build_jinja_env`: autoescape só em `*.html` / `*.html.j2` (e htm/xml) |
| `tests/templates/test_telegram_render.py` | casos aspas/`#`/`&` na URL |
| `specs/SPEC_046_telegram-escape-hash.md` | este arquivo |

## System design

`render_telegram` já chama `escape_markdown_v2` em cada campo de texto (`_escape_items`) e só depois interpola `telegram.md.j2`. O env Jinja é compartilhado com o e-mail (`build_jinja_env`). Hoje `select_autoescape(["html", "j2"])` liga HTML escape em **todo** `.j2`. MarkupSafe converte `"` → `&#34;` e `'` → `&#39;`; o `#` dessas entidades não passa por `escape_markdown_v2` (já rodou antes). `#` literal no título já era escapado — por isso o repro sintético da issue não reproduziu.

Contrato Telegram MarkdownV2 (`regras/50`): escape via `security/markdown_escape.py`, nunca à mão no call site. Templates HTML continuam com autoescape (`regras/60`).

## Decisões e alternativas descartadas

- **Decisão:** callable de autoescape por nome do template (HTML sim, Markdown não). **porquê:** corrige a causa; e-mail XSS permanece. **descartado:** (a) re-escapar `#` depois do render — mascararia entidades e quebraria formatação intencional; (b) dois `Environment` separados — equivalente, mais superfície; (c) `| safe` no template Telegram — frágil, campo novo esquece.

## Métodos e melhores práticas obrigatórias

- Escape MarkdownV2 só em `markdown_escape.py` (`50`).
- E-mail: `autoescape` HTML obrigatório; testes XSS existentes em `test_email_render.py` não podem regressar (`60`, `70`).
- Correção de bug exige teste de mutação (`70`): aspas no título → ausência de `&#` no Telegram; reverter o callable → o teste novo falha.
- `original` write-once: não alterar conteúdo coletado; só a camada de render.

## Plano de execução

1. Substituir `select_autoescape(["html", "j2"])` por callable que retorna True só para sufixos HTML/XML.
2. Testes Telegram: título/resumo com `"` e `'`; título com `#tema`; URL com `&` e fragmento `#`.
3. Rodar pytest focal Telegram + XSS e-mail + ruff/mypy do módulo.

## Riscos e armadilhas

- Desligar autoescape em `.j2` inteiro quebraria XSS do e-mail (`email.html.j2` termina em `.j2`, não em `.html`). O callable **precisa** casar `.html.j2`.
- `PYTHONPATH=src` se o `.venv` da worktree não existir (`70`).
- Snapshot e-mail: não deve mudar se o callable preservar HTML.

## Critério de aceite

- [ ] `render_telegram` de documento com `"` / `'` no título ou resumo **não** contém `&#`.
- [ ] `#` literal no título/resumo aparece como `\#`.
- [ ] `&` na query da URL permanece `&` (não `&amp;`) dentro de `[Abrir original](url)`.
- [ ] `render_email` continua convertendo `<script>` em `&lt;script&gt;`.
- [ ] Digest com esses documentos gera MarkdownV2 sem `#` nu fora de URL.

## Plano de validação (gates a rodar)

```bash
ruff check src/monitoritcd/notifiers/email_notifier.py tests/templates/test_telegram_render.py
ruff format --check src/monitoritcd/notifiers/email_notifier.py tests/templates/test_telegram_render.py
mypy src/monitoritcd/notifiers src/monitoritcd/security
pytest tests/templates/test_telegram_render.py tests/templates/test_email_render.py tests/security/test_markdown_escape.py tests/unit/test_telegram_notifier.py -v
```

## Evidência exigida no relatório

Saída literal dos comandos acima (exit 0). Trecho do `render_telegram` com aspas (sem `&#34;`) e com `#` (`\#`).

## Registro do R (revisão do plano)

- Furo: “escapar `#` de novo no template” quebraria `*bold*` / links. Resolvido: não tocar no Markdown já escapado; só não HTML-escapar.
- Furo: `select_autoescape` default `('html','htm','xml')` **não** pega `email.html.j2` (sufixo real é `.j2`). Resolvido: callable com `.html.j2`.
- NUNCAs: sem fato normativo, sem secret, sem `git add .`, sem produção.
