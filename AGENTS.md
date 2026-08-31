# MonitorITCD

Monitor de mudanças legislativas, normativas e jurisprudenciais em ITCD, sucessões e regime de bens. Coleta pública com proveniência. Classificação por LLM sem reescrever o texto original. Python 3.11+, Firebase.

## Precedência

1. Este `AGENTS.md`.
2. `/home/ailtonganem/Projetos/Skill/AGENTS.md`, só no que este arquivo não especificar.
3. Skill cujo gatilho em `/home/ailtonganem/Projetos/Skill/ATIVACAO.md` casar.
4. Documento auxiliar ou histórico.

`CLAUDE.md` é adaptador e não redefine esta precedência.

## Limites

- Não invente ementa, lei, número, alíquota ou jurisprudência. Conteúdo coletado permanece verbatim.
- Segredos fora do git (`.env` gitignored). Não abra, não commite, não copie valor.
- Não altere Functions, Rules, IAM nem rode deploy.
- Git de escrita (commit/push) fica com o coordenador. Preserve WIP.

## Risco (R0/R1/R2)

Classificação e processo: `/home/ailtonganem/Projetos/Skill/AGENTS.md`. Na dúvida, suba um nível.

Gatilhos locais de `R2`: Functions, Rules/IAM, conteúdo jurídico, CI/release, `deploy-functions.yml`, dado pessoal.

## Comandos canônicos

Fonte: `pyproject.toml` e `.github/workflows/`. Verde = exit 0 e saída literal. Não invente comando.

- Suíte local: `pytest` (`[tool.coverage.report] fail_under = 95`)
- Integridade CI: `ruff check .`, `ruff format --check .`, `mypy`
- Segurança CI: `bandit -c pyproject.toml -r src/ -ll`, `ruff check . --select S`, `python scripts/check_secret_literals.py`

## CI existente (não criar job novo)

- `.github/workflows/tests.yml`: lint, mypy, `pytest --cov=src/monitoritcd --cov-fail-under=95` (3.11/3.12/3.13)
- `.github/workflows/security.yml`: bandit, ruff -S, gitleaks, detect-secrets, pip-audit, lint YAML de sources, SBOM
- `.github/workflows/codeql.yml`, `.github/workflows/mutation.yml` (semanal)
- Operacionais: `actionlint.yml`, `backup.yml`, `commitlint.yml`, `digests.yml`, `grant-sa-roles.yml`, `monitor.yml`, `pages.yml`, `reprocess.yml`, `scorecard.yml`, `secret-rotation-reminder.yml`, `seed-active-states.yml`, `setup-telegram-webhook.yml`
- `.github/workflows/deploy-functions.yml` existe e publica Cloud Functions — **não executar**.

Não há entrypoint local de release. Produção só via workflow remoto, e mesmo assim exige pedido expresso.
