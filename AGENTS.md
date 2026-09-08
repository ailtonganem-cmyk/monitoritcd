# MonitorITCD



Monitor de mudanças legislativas, normativas e jurisprudenciais em ITCD, sucessões e regime de bens. Coleta pública com proveniência. Classificação por LLM sem reescrever o texto original. Python 3.11+, Firebase.

## Precedência

1. Este `AGENTS.md`.
2. `/home/ailtonganem/Projetos/Skill/AGENTS.md`, só no que este arquivo não especificar.
3. Skills de sessão/fila (`iniciar`, `contexto`, `tarefas`, `handoff`, `adaptive-effort-router`) se o gatilho casar.
4. Documento auxiliar ou histórico.

`CLAUDE.md` é adaptador e não redefine esta precedência.

## Roteamento de esforço (automático)
Antes de planejar, executar ou despachar qualquer subtarefa, aplique a skill `adaptive-effort-router` (`~/Projetos/Skill/adaptive-effort-router/SKILL.md`).
Três eixos distintos: (1) papel de modelo adequado; (2) esforço cognitivo C0–C5; (3) risco operacional R0–R3 com controles. Risco **não** sobe esforço. `max` só no núcleo extremo. Decomponha tarefa grande.
Uma linha no relatório, sem chain-of-thought: `Rota: C? | R? | papel | esforço | verificação`.
Se a plataforma não deixar trocar modelo/esforço: roteamento consultivo ou emulado — não afirme que alterou o que não alterou.
O PREVC deste arquivo continua válido; esta skill só escolhe capacidade e profundidade.

<!-- project-lessons-library:begin v2 -->
## Biblioteca de aprendizados e insights do projeto

A skill `project-lessons-library` está disponível. No início da sessão, apenas
reconheça esta política; não carregue a skill nem leia `.agent-library/` por
inteiro. Ative-a ao investigar erros, falhas de build/test/runtime/deploy, antes
de repetir uma correção malsucedida, ao trabalhar em área com armadilhas,
invariantes ou decisões conhecidas, e depois de comprovar um aprendizado ou
insight não óbvio que possa tornar trabalhos futuros materialmente mais rápidos,
seguros ou corretos. Pesquise primeiro o índice local e leia somente os registros
mais relevantes. Registre apenas conhecimento comprovado, não trivial, acionável
e reutilizável; não registre observações rotineiras. O conhecimento local
prevalece sobre o compartilhado e todo registro deve ser revalidado contra o
código, as configurações e os requisitos atuais.
<!-- project-lessons-library:end -->

<!-- autonomo:begin v1 -->
## Modo autônomo (somente `/autonomo`)

A skill `autonomo` está instalada. **Não** carregue o corpo e **não** entre em
modo autônomo por conta própria, nem porque existe backlog, plano ou tarefa
aberta. Ative **somente** se o usuário invocar `/autonomo` (Codex `$autonomo`)
nesta sessão. Sem esse comando, ignore.
<!-- autonomo:end -->

<!-- novahabilidade:begin v1 -->
## Nova habilidade (pesquisa YouTube → skill)

A skill `novahabilidade` está disponível. No início da sessão, apenas reconheça
esta política; não carregue o corpo. Ative-a quando a tarefa exigir domínio que
você não tem completo, ou quando o usuário pedir para pesquisar um tema no
YouTube e transformar em skill reutilizável. Selecione os 20 principais vídeos
dos últimos 6 meses, exporte transcrições, consolide uma skill com mais peso
nos pontos que se repetem, instale em `~/Projetos/Skill` e propague com
`instalar.sh`. Não invente fatos de memória nem copie skill de terceiro.
<!-- novahabilidade:end -->

<!-- grafica:begin v2 -->
## Gráfica e qualidade visual

A skill `grafica` está disponível. No início da sessão, apenas reconheça esta
política; não carregue o corpo. Ative-a em tarefas de renderização, gráficos de
boa qualidade, imagens, mockups, conceitos visuais ou UI/design visual. Fluxo:
ensure Blender+MCP (porta 9876) **pelo agente, sem perguntar** → brief → conceito
→ iterações → gate de qualidade antes de entregar. Blender é o padrão; Figma é
apoio; MCPs pagos só sob pedido explícito.
<!-- grafica:end -->

<!-- vibecode:begin v1 -->
## Vibecode (sob demanda)

A skill `vibecode` está disponível. Na abertura, só reconheça; não carregue o
corpo. Ative em loops FE/BE/DB/UI ou com `/vibecode`. Checklists curtos
(orquestração, tokens, segurança, FE, BE/DB, tasks) sem reabrir PREVC, sem
subir R e sem inventar suíte. Alias: `/vibecoding`.
<!-- vibecode:end -->

<!-- mannered-prose:begin v1 -->
## Estilo: prosa direta (mannered-prose)

Prosa afetada (*mannered prose*) troca afirmação direta por metáfora e floreio.
Em vez de "um parâmetro que vale variar", escreve "a dial worth turning";
em vez de "este ponto ainda importa", escreve "this point earns its keep".
Essas frases exibem o escritor, não a ideia — e o leitor percebe. Irritam
porque fazem o leitor trabalhar mais para o escritor se exibir; também são
imprecisas: metáforas trazem conotações que você não escolheu nem controla.
A correção é dizer o que se quer dizer. Quando houver frase literal, use-a.
Aplique em chat, commits, PRs, planos e documentação gerada nesta sessão.
<!-- mannered-prose:end -->

## Limites

- Não invente ementa, lei, número, alíquota ou jurisprudência. Conteúdo coletado permanece verbatim.
- Segredos fora do git (`.env` gitignored). Não abra, não commite, não copie valor.
- Não altere Functions, Rules, IAM nem rode deploy.
- Git de escrita (commit/push) fica com o coordenador. Preserve WIP.

## Risco (R0/R1/R2)

Classificação: `/home/ailtonganem/Projetos/Skill/AGENTS.md` só preenche lacuna. Processo = ciclo PREVC neste arquivo. Na dúvida, suba um nível.

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

## Ciclo PREVC (obrigatório, curto)
- **P**lanejar: R0 microplano no relatório. R1+ plano curto no chat (problema, escopo/fora, arquivos, aceite, reversão). Sem arquivo SPEC. Sem troca de sessão.
- **R**evisar: R0 não exige. R1/R2 um revisor ≠ autor no diff atual. Achado só bloqueia com requisito violado ou caminho real de impacto. Correção de teste não reabre o plano.
- **E**xecutar: fatia verificável. Vermelho → corrige código e re-roda o mesmo gate.
- **V**erificar: comando real + exit 0 + SHA. Markdown não substitui.
- **C**oncluir: encerre frentes. Handoff só se a frente continuar viva.

## Suíte completa (obrigatório, sem burocracia)
Suíte completa = pytest **uma vez** no SHA. Depois de correção: o teste que falhou + regressão mapeada. Não repetir por classe ritual. Proibido skip/only. Markdown não substitui comando real.
Release/HML de SHA já validado: entrypoint fail-closed do próprio AGENTS, uma vez. Produção = pedido expresso. Não abra PREVC de produto só para publicar o mesmo SHA.
Ciclo operacional: PREVC neste AGENTS.md. Skills de sessão/domínio conforme `Skill/CATALOGO-SKILLS.md` e `Skill/ATIVACAO.md` (corpo só no gatilho).

<!-- orca-worktree-cleanup-policy -->
## Worktrees Orca — limpeza após merge

Após a tarefa do worktree ser mergeada/incorporada à branch principal (`main`/`master` conforme o repo), a worktree Orca e a branch local correspondente **devem** ser removidas — não deixar lixo no projeto.

- Preferir: `orca-ide worktree rm --worktree … --force --json` (Linux: sempre `orca-ide`, nunca `orca` nu) ou exclusão pela UI do Orca.
- Não tentar apagar a worktree de dentro dela se isso falhar; pedir limpeza de fora / script / usuário.
- Isto é política para agentes; a limpeza automática confiável é o timer do sistema `orca-worktree-cleanup`.
<!-- /orca-worktree-cleanup-policy -->

<!-- EAW:BEGIN -->
## EAW — roteamento por complexidade

Este bloco não redefine a precedência no topo deste arquivo.

No primeiro turno de qualquer tarefa de implementação, correção, feature, refactor ou pesquisa de produto:

1. Ler este `AGENTS.md` e o `Skill/AGENTS.md`.
2. Abrir o skill `eaw-router` (canônico em `/home/ailtonganem/Projetos/Skill/eaw/skills/eaw-router`).
3. Gravar `_trabalho/EAW_ROUTE_<id>.md` se este repo usar `_trabalho/`; senão, imprimir o YAML no chat.
4. Seguir a trilha A, C ou B. Default = A (método atual deste repo).
5. TRACK_A e TRACK_C continuam exigindo SPEC e os executores já existentes.
6. TRACK_B só gera código depois de Implementation readiness.
7. Review de TRACK_B/C usa modelo diferente do que escreveu.
8. Epic novo em TRACK_B volta para arquitetura, não para o editor.

Eval design é gate, não documentação opcional. Sem critério observável, a story não avança.
<!-- EAW:END -->

