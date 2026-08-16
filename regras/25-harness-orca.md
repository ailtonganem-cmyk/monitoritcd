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

## Onde a tarefa roda — worktree por FRENTE, não por tarefa [founder 2026-08-16]

> **Problema que esta regra resolve:** uma worktree por tarefa polui o Orca —
> chegamos a 36 workspaces, a maioria sem terminal vivo. A worktree passa a ser
> a **frente de trabalho** (assunto/área), que acumula as tarefas daquele
> assunto; tarefa nova só ganha checkout novo quando há motivo técnico.

**Árvore de decisão — o orquestrador para na primeira que se aplicar:**

1. **É continuação, correção ou complemento** de algo que está numa worktree
   ativa (fix do que acabou de sair, teste que faltou, ajuste pedido na revisão)
   → **roda NELA**:
   `orca orchestration worker-start --task <id> --worktree current --agent <id> --json`
   ou, sem tracking, `orca terminal create --worktree active --command "<agente>" --json`.
2. **É da mesma frente** — mesmos arquivos, módulo ou feature de uma worktree
   ativa — e **não** há paralelismo conflitante → **roda NELA, em sequência**.
3. **É pequena e independente**, do dia corrente → vai para a **worktree do dia**
   (`dia-AAAA-MM-DD`) ou para o **pool** (`w1`…`w3`), reaproveitada por todas as
   tarefas Diretas do dia.
4. **Só então worktree nova**, e apenas por motivo técnico declarado:
   paralelismo real com risco de conflito nos mesmos arquivos · refactor amplo ·
   **base branch diferente** · experimento descartável · trilha Gauntlet de alto
   risco.

Complementos:

- **Nome por frente, não por tarefa** (`aud27`, `fdr-rural`, `dia-2026-08-16`).
  O comentário do card lista as tarefas que a frente acumulou.
- **Teto de worktrees de tarefa por repositório: 6** (fora os checkouts
  principais e o pool). Atingido o teto, **reconciliar antes de abrir outra**.
- `--worktree current` → terminal novo no checkout atual, sem rodar setup.
- `--worktree new-child` / `new-top-level --name <slug>` → checkout novo
  (`--setup run` quando os gates precisarem de dependências).
- **Antes de reutilizar worktree do pool, confirme que está livre**
  (`git status --short` vazio): pool pode ter sido ocupado por outra frente, e
  **trabalho não commitado de terceiro nunca é limpo nem sobrescrito** (`80`, `90`).

## Ciclo de vida da worktree — liberar ≠ remover [founder 2026-08-16]

**No Orca, encerrar/liberar o worker fecha o terminal e arquiva a execução, mas
a worktree continua existindo até um `orca worktree rm`.** Sem esse passo, o
workspace acumula.

| Situação da worktree | Ação |
| --- | --- |
| Tarefa **integrada e validada**, árvore limpa, sem valor de diagnóstico | **Remover** (`orca worktree rm`) |
| Tarefa **parcial, bloqueada** ou com **patch ainda não integrado** | **Manter**, com **nome e comentário de estado** dizendo o porquê e o que falta |
| **Pool pré-aquecido** (`w1`…`w3`) | **Manter** apenas o conjunto pequeno previsto nas regras — nunca crescer o pool por conveniência |
| Worktree **de outro operador/agente** ou com processo vivo | **Não tocar** — nem remover, nem trocar de branch (`90`) |

**Checklist obrigatório antes de remover — as quatro confirmações:**

```bash
orca worktree show --worktree <selector> --json   # 1) liveTerminalCount == 0 e status inativo
git -C <path> status --short                      # 2) árvore limpa (saída vazia)
git -C <path> log --oneline -1                    # 3) commit integrado no branch principal
                                                  #    (git branch --contains <sha> confirma)
                                                  # 4) nenhuma evidência exclusiva ali (SPEC,
                                                  #    relatório, log de validação) — se houver,
                                                  #    mover para o repositório antes
orca worktree rm --worktree <selector> --json
```

Falhou qualquer uma das quatro → **não remove**; registra o motivo no comentário
e mantém.

**Reconciliação:** ao fechar um ciclo/promoção, varrer `orca worktree ps --json`,
classificar cada workspace pela tabela acima e **remover somente as finalizadas
com segurança**. Worktree antiga **não é** sinônimo de tarefa ativa — várias são
preservadas de propósito por patch parcial ou bloqueio; a classificação é
individual, nunca em lote por idade.


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
