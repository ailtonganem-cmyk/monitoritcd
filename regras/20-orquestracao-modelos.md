# 20 — Papéis e agentes [dono 2026-08-16 v6]

> Fonte da verdade de **quem faz o quê e com qual agente**. Três papéis apenas —
> orquestrador, executor, revisor (`10`). Esta versão **substitui integralmente**
> as tabelas e ritos anteriores (cinco papéis, titulares/substitutos cruzados,
> roteamento por limiar, colegiados, rito 2+1, despacho por SPEC formal).

## Orquestrador

**Pensamento, planejamento e gerência.** Entende o problema, escreve o **plano
de trabalho** com a spec e o **nível da tarefa**, **escolhe executor e revisor**
e o **esforço** de cada um, despacha, acompanha, integra no branch principal,
reporta e segue para a próxima tarefa.

- É o **único que usa git para escrever** (commit, merge).
- Não codifica: fechado o plano, delega. Exceção: autorização expressa do
  dono ou tarefa de documentação/regra que ele mesmo conduz.

## Executor — escolhido pelo nível e pela qualificação

| Nível da tarefa | Executores preferenciais |
| --- | --- |
| **Simples** | **Grok** · **opencode — DeepSeek v4 Pro** · Claude **Sonnet 5** · ChatGPT **Luna** |
| **Média** | **Grok** · Claude **Sonnet 5** · ChatGPT **Terra** · **opencode — DeepSeek v4 Pro** |
| **Complexa** | **Grok** · Claude **Opus 5** · ChatGPT **Terra** |

- **O Grok está habilitado para os três níveis** — simples, média e complexa.
- A escolha considera a **qualificação do agente para aquele tipo de trabalho**
  (linguagem, stack, natureza da mudança), não só o nível.
- O **esforço** (alto, extra alto, máximo) é definido pelo orquestrador no plano.
- Executor **não usa git para escrever**; leitura (`diff`, `log`, `status`,
  `show`) é livre.
- Executor sem plano ou sem critério de aceite **pergunta antes de improvisar**.

## Revisor

**Claude Code Opus 5** ou **ChatGPT Terra (ou superior)**, escolhido pelo
orquestrador. Verifica e valida se **o que foi planejado foi efetivamente
realizado e está correto**: roda os gates (`70`), confere o resultado contra o
plano e devolve com o que faltou ou aprova. **Nunca é o agente que executou.**

## Despacho

1. O despacho carrega **o plano** — objetivo, spec, arquivos, critério de aceite
   e como validar.
2. Ao lançar subagente Claude, passar `model` **explicitamente** (`opus`,
   `sonnet`) — sem o parâmetro ele herda o modelo da sessão.
3. Agentes de outros fornecedores (ChatGPT/Codex, Grok, opencode) rodam em
   terminal próprio; o retorno é o **relatório com a evidência dos gates**.
4. Paralelizar só quando houver ganho real e arquivos disjuntos.
5. **Proibido o tool `Workflow`/ultracode.**
6. **Tudo roda no branch principal** — sem worktree (`80`).

## Comunicação e registro entre agentes [dono 2026-08-16]

**Toda etapa concluída é comunicada a quem depende dela, e tudo fica
documentado.** Nenhum agente encerra em silêncio e nenhum handoff fica sem
resposta.

- **Executor → orquestrador:** ao terminar, relata o que fez, os arquivos
  tocados, a **saída literal dos gates** e o que ficou pendente.
- **Revisor → orquestrador:** relata o veredito — aprovado, ou o que faltou —
  com a evidência que o sustenta.
- **Orquestrador → executor/revisor:** confirma o recebimento e informa a
  decisão (integrado · devolvido para ajuste · escalado), **fechando o ciclo**.
- **Orquestrador → dono:** reporta a conclusão com a evidência e o
  **roteamento real** — quem executou, quem revisou, com que modelo e esforço.
- **Registro:** cada relatório fica documentado no canal da tarefa e, quando
  gerar conhecimento durável, no repositório (`80`). **Handoff sem registro não
  conta como concluído.**
## Limites que a orquestração não dissolve

Nenhuma escolha de agente ou consenso autoriza violar as NUNCAs (`90`) nem
produz fato normativo (`40`). Dinheiro, remoção de funcionalidade, ação
destrutiva e dado real de terceiros são sempre do dono.
