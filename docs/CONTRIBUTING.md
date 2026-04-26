# CONTRIBUTING.md

Guia para contribuir ao MonitorITCD. **Sistema de uso pessoal** — colaboração
externa não esperada, mas o guia documenta as expectativas para o caso do
Claude Code (única implementação) operando.

## Princípios canônicos

Antes de qualquer alteração, leia [CLAUDE.md](../CLAUDE.md) seção 🛡️.
Os 3 princípios são **inegociáveis**:

1. 🔒 **Backend nunca confia em entrada externa** (incluindo bot do dono)
2. 📏 **`input_limits` obrigatórios** em todo modelo de entrada
3. 🔐 **Secrets PROIBIDOS em código fonte** (sem `--no-verify`)

## Padrões de código

- **PT-BR** em comentários, docstrings, mensagens de erro pra usuário, commit messages, PR descriptions.
- **Inglês** em identificadores (variáveis, funções, classes, módulos).
- Type hints obrigatórios em toda função pública.
- `mypy --strict` em `core/`, `filters/`, `notifiers/`, `security/`.
- Async first em collectors e bot. Nada de `requests` síncrono.
- Pydantic em toda fronteira de processo.

## Estilo

- Comente o **porquê**, nunca o **o quê**.
- Nomes em inglês (exceto termos jurídicos: `causa_mortis`, `espolio`, etc.).
- `ruff format` e `ruff check` obrigatórios antes de commit.

## Estratégia de testes

- Cobertura ≥ 95% global, 100% em módulos críticos.
- Pirâmide: unit (~70%) → integration (~25%) → e2e (~5%).
- Snapshot tests obrigatórios para templates (qualquer mudança requer aprovação `--snapshot-update`).
- Property-based testing com `hypothesis` em parsers e sanitizers.
- Mutation testing semanal (`mutmut`).

## Workflow de PR

1. Criar branch a partir de `main`.
2. Fazer mudanças com testes.
3. `pre-commit run --all-files` (deve passar).
4. `pytest tests/` deve passar verde.
5. Commit message segue formato:
   ```
   feat(escopo): descrição curta

   Detalhes do PR.

   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   ```
6. Abrir PR; CI roda 6 checks (lint, mypy, pytest, SAST, secret scan, dep audit).
7. **Todos os checks devem ser verdes** antes de merge (gate strict).

## Adicionar uma fonte nova

Ver [docs/RUNBOOKS.md](RUNBOOKS.md) seção "Adicionar fonte".

## Rotação de secrets

Lembrete mensal automático via Telegram. Procedimento em
[docs/RUNBOOKS.md](RUNBOOKS.md) seção "Rotação".

## Reportar bugs / pedir features

Issues no GitHub do repo (privado). Use template padrão.
Ideas vão para `IDEAS.md` (cardápio); decisões arquiteturais para `docs/adr/`.
