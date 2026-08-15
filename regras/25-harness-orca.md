# 25 — Harness Orca: orquestração nativa, papéis e limites [founder 2026-08-14 v4]

> **Fonte da verdade de COMO operar a malha de agentes.** O Orca ADE é o harness
> principal; sua camada de orquestração (`orca orchestration ...`) **substitui o
> ritual manual** que a documentação antes descrevia em prosa (arquivo de estado,
> declaração de arquivos, cobrança de retorno, contagem de rodadas).
> **Esta determinação prevalece sobre qualquer disposição local divergente.**
>
> Antes de operar, carregue o guia version-matched: `orca skills get orca-cli` e
> `orca skills get orchestration` — os comandos mudam entre versões e **este
> módulo não substitui o guia do binário**; ele fixa *como o projeto usa* o que o
> guia oferece.

## Por que nativo

| O que fazíamos à mão | O que o Orca já faz |
| --- | --- |
| `_trabalho/ESTADO_<id>.md`, declarar arquivo antes de editar | `worktree set --comment` + `--workspace-status` + estado de Task/Dispatch |
| Tasklist em markdown, ordem na cabeça | `run-create` + `task-create --deps` = **DAG com dependências** |
| SPEC colada no prompt, relatório em prosa | `worker-start --agent --model --effort` + `worker_done --outcome --files-modified` |
| "Aguardar o executor e cobrar" | `check --wait --types worker_done,escalation,question` |
| Perguntar ao founder no meio | `ask`/`reply` (worker→coordenador) · `gate-create`/`gate-resolve` (decisão de DAG) |
| Contar rodadas para não repetir erro | **circuit breaker nativo**: 3 falhas na mesma task ⇒ `failed` |

Regra prática: **se o Orca tem comando, não escreva protocolo** — use o comando e
registre a evidência. Arquivo de estado só para agente fora do Orca (`30`).

## Ciclo canônico da tasklist (Gauntlet de fila)

```bash
# 1. Abrir o ciclo com objetivo E barra mínima declarada (10)
orca orchestration run-create --objective "<ciclo> — barra: <critérios verificáveis>" --json

# 2. Decompor a fila em tasks com dependências reais
orca orchestration task-create --spec "<item>" --json
orca orchestration task-create --spec "<item dependente>" --deps '["<task_id>"]' --json
orca orchestration task-list --ready --brief --json

# 3. Despachar TODOS os workers independentes antes de esperar
orca orchestration worker-start --task <id> --worktree current --agent codex --model gpt-5.6-terra --effort xhigh --json
orca orchestration worker-start --task <id> --worktree new-top-level --name <slug> --agent claude --model opus --effort high --setup run --json

# 4. Esperar por evento, nunca por polling
orca orchestration check --wait --types worker_done,escalation,question --timeout-ms 900000 --json
#    responder perguntas: orca orchestration reply --id <msg_id> --body "<resposta>" --json
#    liberar worker concluído: orca orchestration worker-release --dispatch <id> --json
#    só então: orca orchestration check --ack <delivery_id> --wait ... --json

# 5. Gate de fila — a barra mínima foi atingida?
orca orchestration gate-create --task <id> --question "Barra atingida?" --options '["sim","não — maior gap: ..."]' --json
orca orchestration gate-resolve --id <gate_id> --resolution "<decisão>" --json
```

- **Timeout de `check --wait` é checkpoint, não falha** — tarefa de codificação
  roda 15–60 min; siga esperando em janelas rolantes.
- **Heartbeat e atividade no terminal significam vivo, não pronto.** Nunca matar
  worker por silêncio.
- `worker_done` válido **fecha a task automaticamente** — não chamar
  `task-update --status completed` depois.

## Limites de uso — roteamento automático por limiar [founder 2026-08-14 v4]

O medidor é nativo e **deve ser consultado ao abrir cada tarefa/ciclo**:

```bash
orca account list --json    # → result.rateLimits por provedor
```

Cada provedor traz `session` (janela curta) e/ou `weekly` com `usedPercent` e
`resetsAt`; Claude traz ainda `fableWeekly` (cota específica do Fable).

| Faixa de `usedPercent` (semanal do papel) | Ação do orquestrador |
| --- | --- |
| < 85% | usar o **titular** do papel |
| **≥ 85%** | titular **sai da vez**; entra o **substituto 1** (registrar no relatório) |
| **≥ 95%** ou `status: error` | só com ordem expressa do founder; senão, próximo substituto |
| todos esgotados | registrar o bloqueio, informar `resetsAt` e aguardar a janela |

- **Não** consultar antes de cada despacho — uma leitura por tarefa/ciclo basta
  (orçamento, não checagem contínua).
- `status: "error"` / `"unavailable"` **não** é o mesmo que cota cheia: pode ser
  sessão expirada (ex.: Grok pedindo re-login, opencode sem cookie). Nesse caso,
  informar o founder o que reautenticar — **credenciais nunca passam pelo agente**.
- O **roteamento efetivo** (quem realmente rodou cada papel) entra no relatório
  final — nunca afirmar ter usado um modelo que não estava disponível.

## Placement e worktree

- `--worktree current` → terminal novo no checkout atual, sem rodar setup.
- `--worktree new-child` / `new-top-level --name <slug>` → checkout novo
  (`--setup run` quando os gates precisarem de dependências).
- **Antes de reutilizar worktree do pool, confirme que está livre**
  (`git status --short` vazio): worktree de pool pode ter sido ocupada por outra
  frente, e **trabalho não commitado de terceiro nunca é limpo nem sobrescrito**
  (`80`, `90`).

## Visibilidade — status do card

Todo agente atualiza o cartão da sua worktree em marcos reais:

```bash
orca worktree set --worktree active --comment "gates verdes; aguardando crítico" --json
orca worktree set --worktree active --workspace-status in-review --json   # todo|in-progress|in-review|completed
```

## Limites que o harness não dissolve

Comando de orquestração não cria autorização: NUNCAs e perguntar×agir (`90`),
fatos protegidos (`40`) e os gates de release (`60`, `70`) valem integralmente.
`orchestration reset` é recuperação — nunca durante coordenação ativa.
