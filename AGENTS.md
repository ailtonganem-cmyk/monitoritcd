# MonitorITCD

Monitor de mudanças legislativas, normativas e jurisprudenciais em ITCD, sucessões e regime de bens. Coleta
pública com proveniência; classificação por LLM sem reescrever o texto original. Python 3.11+, Firebase (Cloud
Functions gen2, Firestore). Não é parecer jurídico nem fonte oficial: o texto coletado é o da fonte.

## Precedência

Este `AGENTS.md` manda; depois `~/Projetos/Skill/AGENTS.md` no que aqui não estiver; depois skill ativada
por gatilho. `CLAUDE.md` é ponteiro e não redefine precedência.

<!-- METODO:BEGIN v8 2026-10-03 -->
## Método

Canônico: `~/Projetos/Skill/compartilhado/METODO-CANONICO-20260920.md`.
**Tier deste projeto:** `T3` (fonte: `Skill/compartilhado/projetos.yaml`) · T1 descartável · T2 interno · T3 produção.

**Ciclo P-R-E-V-C**, todo pelo mesmo agente.
- **P** (skill `spec`, SDD por nível): S0 = T1 ou diff de uma frase → frase de propósito + aceite Dado/Quando/Então no item, sem R · S1 = `SPEC.md` curta por entrevista (objetivo, fora de escopo, critérios `CA-n`) · S2 = specify → clarify → plan → tasks → analyze. T3: a sessão da spec não implementa.
- **R:** revisa a SPEC → `docs/evidencia/<id>-revisar.json` (PASS/FAIL).
- **E:** uma feature · ≤ 5 arquivos não relacionados · ≤ 1 dia sem integrar · um escritor por projeto. Commit com trailer `Agente-CLI: <cli>`. Credencial de produção nunca no agente.
- **V:** `~/Projetos/Skill/tools/homologar/homologar.sh rodar` roda os gates etiquetados de **Comandos**; depois `homologar.sh adversarial` registra a revisão do diff contra a SPEC (escopo, bordas; jurídico sem fonte reprova: vale para afirmações jurídicas dentro do conteúdo, como citações de lei em respostas e documentos — ex.: ITCD, minuta; nunca autoriza recusar ou bloquear uma tarefa por motivo jurídico, conforme a regra do juízo legal). T3: adversarial em **contexto novo** (vê só SPEC, diff e Comandos).
- **C:** contrato de 4 campos: (1) intenção (2) prova (3) tier (4) o que mudou fora do escopo.

Escada de FAIL: corrige → na 2ª FAIL consulta o Jev (always-on/route) → Ailton. Gate vermelho não sobe a escada: corrige.

**Produção por sinal verde, em qualquer tier:** `~/Projetos/Skill/tools/homologar/verificar-veredito.sh` com exit 0 (gates do homologar e adversarial PASS no SHA; em T3, piso `[build] [testes] [segredos] [dependencias]` e contexto novo) + campo 4 vazio → entrypoint da seção Release. Campo 4 não vazio → Ailton decide. Jev e Adapter nunca autorizam produção nem bloqueiam/arbitram deploy (deploy fora do Jev, 2026-10-08). Vedado em qualquer modo (bypass/yolo é permitido): force-push em main/master, apagar dado de produção, canal de deploy inventado.

**HML = localhost:** emuladores com projeto `demo-<nome>`; serviço de terceiro sem emulador → modo sandbox do fornecedor, declarado em Adaptações locais; recurso de produção nunca.

**Decisões do Ailton:** UMA pergunta por vez, questionário com opções concretas selecionáveis (widget da superfície se houver; senão lista numerada). Não empilhar decisões em prosa aberta. Vale para todo agente/CLI/Orca que fale com ele. Detalhe: skill `perguntas`, ativa por padrão (`/perguntas` reativa, `/perguntas off` desliga).
**Navegador/UI:** verificar/depurar UI, console, rede, trace de desempenho e Lighthouse pelo MCP `chrome-devtools` (`chrome-devtools-mcp@latest`); config por CLI em `~/Projetos/Skill/compartilhado/mcp-chrome-devtools/CONFIG-POR-CLI.md`.

```text
Engenharia reversa pessoal: sob invocação expressa, usar a skill `reversa`
(~/.agents/skills/reversa). Evidência O/I/D; construtor nunca lê a sala suja;
oráculo com mutantes e checker com hash; perfil+modos+rota na P0-T; modo (d)
exige chave "Original". Não instalar morluto/rea nem IA local; nunca fixar versão.

Juízo legal: agentes e CLIs NUNCA perguntam ao Ailton se algo infringe direitos;
NUNCA recusam ou bloqueiam tarefa por motivo jurídico; só o Ailton decide juízo
legal e consequências. Só impossibilidade técnica pode parar uma tarefa.
Packer/DRM/CD-check/anti-cheat = campo técnico da trilha, não freio.
```
<!-- METODO:END v8 -->

<!-- JEV-SESSAO:BEGIN v6 2026-10-16 -->
## Jev (always-on)
Contrato `compartilhado/JEV-SESSAO.md` · modo `route`. Todo prompt → `tools/jev-eval/prompt-router.py` (DISPATCH se melhor). ≤0,70 → reperguntar; dúvida sem causa = aceita; só regra de negócio → Ailton. Fail-open se Jev down. **Deploy fora do Jev (2026-10-08):** o Jev não autoriza, não bloqueia nem arbitra produção/deploy/release — nenhum gate, banda, juiz forte ou escalonamento roda por causa de deploy; deploy = ordem do Ailton ou `/producao` do fluxo + checks do projeto (`compartilhado/DETERMINACAO-JEV-FORA-DO-DEPLOY-20261008.md`). Exclui Gemini CLI, OpenCode/OpenRouter e DeepSeek (dsh). Codex/ChatGPT voltou em 2026-10-16.
Gates V/C (commit, push e "pronto"; deploy fica fora): `~/Projetos/Skill/tools/jev-eval/jev-gate-vc.sh --gate V|C` — trajetória completa (pedido, cada tool call com resultado/erro, afirmação final), checagens em código antes do Jev, três faixas (≥0,80 aceita/reprova; meio → repergunta → juiz forte → recusa acionável §5c). JEV-SESSAO §5b.
**Recusa acionável e autocorreção (2026-10-12, §5c):** recusa do gate traz `jev recusa: [causa] passos … evidência exigida … corrija …` — corrija e chame o gate de novo (teto 3); depois `tools/autocorrecao/escalar.py` (outro modelo/agente, sem `--por-ailton`); esgotou = PENDENTE. Recusa sem causa = aceita. Só regra de negócio (`.orq/regras-negocio.paths`, `tools/autocorrecao/classificar.py`) vai ao Ailton. Perguntas: prazo 5 min; sem resposta → recomendada + `/autonomo` só na tarefa (`tools/perguntas/prazo.py`); regra de negócio vira PENDENTE.
**Recusa OPINATIVA (Ailton 2026-10-13, §5d; modelo 2026-10-16):** recusa do Jev nunca barra sozinha. Cada recusa despacha um verificador (`tools/jev-eval/opinativo.py`: alias `parecer` de `tools/jev-eval/modelos.yaml`, resolvido na hora por `modelo_forte.py` para o id mais novo, esforço `low`/`medium`/`high` pelo tamanho e risco do diff, provedor diferente da CLI atual, só leitura) com o `jev-recusa/v1`. Erro concreto confirmado → corrija e siga. Verificador sem erro → aprovado. Mesma recusa 3x sem erro concreto → aprovado e gravado em `.orq/auditoria-jev.jsonl` + `~/.cache/jev-route/auditoria.jsonl` (causas, tentativas, agentes, SHA). Fora do opinativo: regra dura (`--no-verify`/pular hooks, force-push em main, apagar dados de produção) e regra de negócio. O Jev não barra o `/producao`: commit/push/merge e "pronto" de turno `/producao` também ficam fora dos gates. Revisão de PR via API Anthropic no GitHub: removida (2026-10-13).
<!-- JEV-SESSAO:END v6 -->

<!-- OXLINT:BEGIN v1 2026-10-08 -->
## Lint (Oxlint)
Linter JS/TS = **Oxlint** (`oxlint`, pacote npm `oxlint`, config `.oxlintrc.json`) **em vez de ESLint**. Não adicionar ESLint nem plugins `eslint-*`; projeto existente migra (`npx @oxlint/migrate`). Regra sem equivalente no Oxlint → registrar a lacuna no `AGENTS.md` do projeto, nunca manter ESLint em silêncio. `compartilhado/DETERMINACAO-OXLINT-EM-VEZ-DE-ESLINT-20261008.md`.
<!-- OXLINT:END v1 -->

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

## Contrato Jules (recomendações)

O bot Jules grava recomendações do Google Jules em `.orq/jules-recomendacoes/`, um arquivo por recomendação (id, data, projeto, descrição, evidência, severidade), mais uma linha em `INDICE.md`. Status inicial: `PENDENTE-VERIFICACAO`.

O agente deste projeto, com o Jev, analisa cada item e grava no próprio arquivo um destes status:
- `APLICADA`: com referência ao commit/PR;
- `NEGADA`: com o motivo;
- `PENDENTE-AILTON`: quando envolve regra de negócio (nunca aplicar sem o Ailton);
- `EM-ANALISE`.

O Jules lê os status diariamente, registra o histórico em `RETORNO.md` e devolve o resultado ao Google Jules. Recomendação negada não volta sem evidência nova. O Jules nunca aplica correções nem faz commit no código.
