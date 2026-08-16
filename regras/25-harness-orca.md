# 25 — Harness Orca ADE: comandos e protocolo de despacho

> Fonte da verdade de **como o despacho do `20` é executado quando o harness é o
> Orca ADE**. Este módulo **não cria método**: o ciclo é o PREVC (`10`), os
> papéis são os do `20`, e as NUNCAs e a tabela perguntar×agir (`90`) valem
> integralmente dentro do Orca. Aqui está só a mecânica.

## Regra zero — a referência de comandos é o binário, não este arquivo

A skill `orca-cli` instalada declara explicitamente que a lista de subcomandos e
flags **muda entre releases** e que o guia completo é servido pelo próprio
binário. Portanto:

```bash
orca skills get orca-cli
orca skills get orchestration
```

**Carregue o guia versionado antes de rodar qualquer comando de Orca.** Não
deduza flag de memória nem deste módulo — o que está aqui é o protocolo estável
(quem faz o quê, em que ordem, com que limites), verificado na versão 1.4.183.
Divergiu do guia do binário, **vale o guia do binário**.

Executável a usar: `orca` no Windows; `orca-ide` no Linux fora de terminal
gerenciado (lá, `orca` puro é o leitor de tela do GNOME e começa a falar na
máquina do usuário). Falhou o executável escolhido → reportar o erro exato e
parar; **não** tentar outro, que pode apontar para outro build.

Pré-condições: `orca status --json` com runtime `ready`; a orquestração é
recurso experimental e precisa estar ligada em *Settings > Experimental*.

## Quando é orquestração e quando é entrega de tarefa

O guia do Orca separa dois regimes, e confundi-los é o erro clássico:

| Situação | Regime | O que usar |
| --- | --- | --- |
| O orquestrador **supervisiona**, espera resultado, coordena dependências | **orquestração** | `run-create` → `task-create` → `worker-start` → `check --wait` |
| Passar a tarefa adiante e **não** acompanhar (entrega de titularidade) | **handoff** | `orca-cli` puro; **não** criar Task/Dispatch nem `check --wait` |

No nosso método o regime normal é **orquestração**: o orquestrador do `20` é o
coordenador, planeja, despacha e valida. Só use handoff quando a intenção for
transferir a titularidade do trabalho.

## Ciclo canônico do coordenador

Crie o Run e **todas** as Tasks independentes antes de iniciar os workers, e
inicie todos os workers independentes antes de esperar:

```bash
orca orchestration run-create --objective "<objetivo da rodada>" --json
orca orchestration task-create --spec "<SPEC de Execução ou seu caminho>" --json
orca orchestration worker-start --task <task_id> --worktree current --agent claude --model opus --effort high --json
orca orchestration check --wait --types worker_done,escalation,question --timeout-ms 900000 --json
orca orchestration worker-release --dispatch <dispatch_id> --json
orca orchestration check --ack <delivery_id> --wait --types worker_done,escalation,question --timeout-ms 900000 --json
```

Pontos que a documentação fixa e que **não** são opcionais:

- **`--worktree current`** — o trabalho roda na árvore principal (`80`). Não
  criar `new-child`/`new-top-level` sem motivo declarado.
- **`--effort` exige `--model`**, e nenhum dos dois combina com `--terminal`
  (só valem para terminal de agente novo). O receipt traz `launch.requested` e
  `launch.effective` — **confira** que o efetivo é o pedido.
- **`--deps <json_array>`** no `task-create` expressa dependência entre tarefas;
  `task-list --ready --json` mostra o que está liberado.
- **Uma Delivery por vez, em FIFO:** o `check` devolve o lote mais antigo e o
  **repete** até o `--ack <delivery_id>`. Processe todas as mensagens do lote
  antes de reconhecer.
- **`question` se responde com `reply`:**
  `orca orchestration reply --id <msg_id> --body "<resposta>" --json`.
- **`worker-release` após cada `worker_done` aceito** (sucesso ou falha), a menos
  que haja tarefa imediata para o mesmo agente — nesse caso,
  `worker-start --task <próxima> --terminal <handle>` transfere a limpeza.
  Quiser manter o terminal vivo para depuração: `worker-retain --dispatch <id>`,
  registrando a exceção — nunca "pular" a limpeza em silêncio.

## O que o Orca já faz — e que não precisa ser reinventado em regra

Boa parte do protocolo manual que já tentamos escrever à mão é **nativa**:

| Necessidade | Mecanismo nativo |
| --- | --- |
| Contrato da tarefa na ida | `task-create --spec` |
| Estado/progresso durante | `check`, `worker-show`, `worker-read`, `heartbeat`, `status` |
| Relatório na volta | `send --type worker_done ... --outcome succeeded\|failed --files-modified` |
| Dúvida bloqueante do executor | `ask` (worker) → `reply` (coordenador) |
| Decisão que é do coordenador | `gate-create` / `gate-resolve` / `gate-list` |
| Dependência entre tarefas | `task-create --deps` |
| Antifalha de repetição | circuit breaker: **3 falhas seguidas** na mesma task → dispatch interrompido e task marcada `failed` |

O ESTADO em arquivo (`30`) continua valendo **fora** do Orca (agentes em janelas
soltas, CLIs de outros fornecedores); rodando pelo Orca, o estado autoritativo é
o do Run/Dispatch.

## Erros de leitura que a documentação desfaz

- **Timeout do `check --wait` ou `{count:0}` não é falha do worker.** Tarefa de
  codificação roda rotineiramente 15–60 minutos. Continue esperando em ondas.
- **Heartbeat e atividade visível no terminal significam "vivo", não "pronto".**
  Não pare, feche nem reinicie worker por ausência de conclusão.
- **Não liberar worker** por timeout, TUI ocioso, heartbeat, status, pergunta,
  escalação ou `worker_done` rejeitado/obsoleto.
- **`worker_done` válido já conclui task e dispatch** — não emendar
  `task-update --status completed`.
- **Não descrever como orquestrado** trabalho que correu fora do Orca. Se correu
  fora, dizer isso com todas as letras; para restabelecer proveniência, rodar de
  novo por um dispatch de verdade.

Verificação de que o despacho existe mesmo:

```bash
orca orchestration task-list --json
orca orchestration dispatch-show --task <task_id> --json
```

## Limites que o Orca não afrouxa

O harness não é fonte de autorização. Continuam valendo, dentro dele:

- **NUNCAs (`90`)** — inclusive a proibição de inventar fato normativo (`40`),
  que nenhum `worker_done` ratifica.
- **Perguntar × agir (`90`)** — billing, `push --force`, delete em massa, dado
  real de contribuinte e decisão de produto **param a linha**, mesmo com o
  coordenador em modo automático.
- **Git é do coordenador (`80`)** — executor, dentro ou fora do Orca, não
  escreve por git; o trabalho é integrado na branch principal, com pathspecs.
- **Revisor ≠ executor (`20`)** — despachar a revisão para o mesmo agente que
  implementou não satisfaz o PREVC, ainda que o Orca aceite.
