# MonitorITCD

Monitor de mudanças legislativas, normativas e jurisprudenciais em ITCD, sucessões e regime de bens. Coleta
pública com proveniência; classificação por LLM sem reescrever o texto original. Python 3.11+, Firebase (Cloud
Functions gen2, Firestore). Não é parecer jurídico nem fonte oficial: o texto coletado é o da fonte.

## Precedência

Este `AGENTS.md` manda; depois `~/Projetos/Skill/AGENTS.md` no que aqui não estiver; depois skill ativada
por gatilho. `CLAUDE.md` é ponteiro e não redefine precedência.

<!-- METODO:BEGIN v5 2026-09-23 -->
## Método

Canônico: `~/Projetos/Skill/compartilhado/METODO-CANONICO-20260920.md`.
**Tier deste projeto:** `T3` (fonte: `Skill/compartilhado/projetos.yaml`) · T1 descartável · T2 interno · T3 produção.

**Ciclo P-R-E-V-C** — o mesmo agente planeja, revisa, executa, valida e conclui.
- **P:** T2/T3 → `SPEC.md` por entrevista (objetivo, fora de escopo, critérios executáveis). T1 ou diff de uma frase → frase de propósito, sem R. T3: a sessão que escreveu a spec não implementa.
- **R:** revisa a SPEC → `docs/evidencia/<id>-revisar.json` (PASS/FAIL).
- **E:** uma feature · ≤ 5 arquivos não relacionados · ≤ 1 dia sem integrar · um escritor por projeto. Commit com trailer `Agente-CLI: <cli>`. Credencial de produção nunca no agente.
- **V:** `~/Projetos/Skill/tools/homologar/homologar.sh rodar` executa os gates etiquetados de **Comandos** e grava a evidência; depois `homologar.sh adversarial` registra a revisão do diff contra a SPEC (escopo, casos de borda; afirmação jurídica sem fonte reprova). T3: a revisão adversarial roda em **contexto novo** (subagente ou sessão nova que vê só SPEC, diff e Comandos).
- **C:** contrato de 4 campos: (1) intenção (2) prova (3) tier (4) o que mudou fora do escopo.

Escada de FAIL: corrige → na 2ª FAIL consulta o Jev (shadow) → Ailton. Gate vermelho não sobe a escada: corrige.

**Produção por sinal verde, em qualquer tier:** `~/Projetos/Skill/tools/homologar/verificar-veredito.sh` com exit 0 (gates do homologar e adversarial PASS no SHA; em T3, piso `[build] [testes] [segredos] [dependencias]` e contexto novo) + campo 4 vazio → entrypoint da seção Release. Campo 4 não vazio → Ailton decide. Jev e Adapter nunca autorizam produção. Vedado em qualquer modo (bypass/yolo é permitido): force-push em main/master, apagar dado de produção, canal de deploy inventado.

**HML = localhost:** emuladores com projeto `demo-<nome>`; serviço de terceiro sem emulador → modo sandbox do fornecedor, declarado em Adaptações locais; recurso de produção nunca.
<!-- METODO:END v5 -->

## Comandos

Linha com etiqueta é gate da Validação (`homologar.sh rodar`); sem etiqueta é informativa. Rodar no `.venv`
(`pip install -e ".[dev]"`). Fonte: `pyproject.toml` e `.github/workflows/tests.yml`, `security.yml`.

- Lint [gate]: `ruff check . && ruff format --check .`
- Tipos [gate]: `mypy`
- Testes [testes]: `pytest --cov=src/monitoritcd --cov-fail-under=95`
- SAST [gate]: `bandit -c pyproject.toml -r src/ -ll && ruff check . --select S`
- YAML de fontes [gate]: `python scripts/lint_sources_yaml.py`
- Segredos [segredos]: `git ls-files -z | xargs -0 -- detect-secrets-hook --baseline .secrets.baseline`
- Dependências [dependencias]: `pip-audit --strict --vulnerability-service osv --ignore-vuln CVE-2026-3219 --ignore-vuln PYSEC-2022-42969 --ignore-vuln GHSA-4xh5-x5gv-qwph --ignore-vuln PYSEC-2025-49`
- Build do painel [build]: `npm --prefix apps/painel run build` (Angular; é o que o Hosting publica, `apps/painel/dist/painel/browser`; pré-requisito `npm ci --prefix apps/painel`)
- Painel HML: `.venv/bin/python -m monitoritcd.main painel --host 127.0.0.1 --port 8765`

CI (não criar job novo): `tests.yml` (lint e build do painel, mypy, pytest com cobertura 95 em 3.11/3.12/3.13), `security.yml`
(bandit, ruff S, gitleaks, detect-secrets, pip-audit, lint YAML, SBOM), `codeql.yml`, `mutation.yml` (semanal),
mais workflows operacionais (`backup`, `digests`, `monitor`, `reprocess`, `seed-active-states` etc.).

## Portas de emulador

Projeto `demo-monitoritcd`. `UI :14000 · Firestore :18080 · Storage :18199 · Auth :19099 · hub :14400`; painel
`http://127.0.0.1:8765` (não `:4200`, que é do SEFWorkStation). Ocupada → varrer a faixa até achar livre e subir
stack próprio. Não reutilizar nem matar emulador alheio sem ordem. Frota: `Skill/compartilhado/ORCA-HML-PORTAS.md`.

## Release

Sem entrypoint local. Produção = workflow remoto `gh workflow run deploy-functions.yml -f sha=<SHA completo de
main>` (Cloud Functions `proxy_br`, `canary_filter`, `bot_webhook` em `southamerica-east1`), só com sinal verde e
o SHA já aprovado por Tests e Security.

## Pós-produção

- Smoke: o passo "Verificar Functions publicadas" do próprio workflow (URI de cada Function).

## Limites

- Não invente ementa, lei, número, alíquota ou jurisprudência. Conteúdo coletado permanece verbatim.
- Segredos fora do git (`.env` gitignored). Não abra, não commite, não copie valor.
- Área sensível (SPEC explícita e revisão adversarial atenta): Functions, Rules/IAM, conteúdo jurídico,
  CI/release, `deploy-functions.yml`, dado pessoal.

## Adaptações locais

Nenhuma.
