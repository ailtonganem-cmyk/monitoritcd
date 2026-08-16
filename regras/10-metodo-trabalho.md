# 10 — Método de trabalho: PREVC [dono 2026-08-16 v6]

> **Método único: PREVC.** Três papéis: **orquestrador**, **executor**,
> **revisor**. Esta versão **substitui integralmente** as regras de método
> anteriores — ficam revogadas trilhas, camadas do Gauntlet, gate de fila, barra
> mínima de ciclo, memória compartilhada em arquivo, papéis de planejador e
> validador separados e a obrigatoriedade de worktree.

## Os três papéis

| Papel | Faz |
| --- | --- |
| **Orquestrador** | Pensamento, planejamento e gerência: entende o problema, escreve o plano de trabalho, classifica o nível, escolhe executor e revisor, despacha, integra e reporta. |
| **Executor** | Codificação, conforme o plano recebido. |
| **Revisor** | Verifica e valida se o que foi planejado foi **efetivamente realizado e está correto**. |

## O ciclo PREVC

1. **P — Planejamento.** O orquestrador entende o problema, mapeia arquivos e
   escreve o **plano de trabalho** (abaixo).
2. **R — Revisão do plano.** O próprio orquestrador confere o plano antes de
   despachar: furos, riscos, conflito com `40`/`90`, alternativa melhor.
3. **E — Execução.** O executor escolhido implementa conforme o plano.
4. **V — Validação.** O **revisor** roda os gates (`70`) e confere o resultado
   contra o plano; devolve com o que faltou ou aprova.
5. **C — Confirmação.** O orquestrador integra, reporta com evidência e segue
   para a próxima tarefa.

**Anti-loop:** até 3 idas e voltas entre executor e revisor; persistindo, o
orquestrador escala ao dono com o que ficou em aberto.

## O plano de trabalho

O orquestrador **apresenta o plano completo** antes de despachar, contendo:

- **objetivo** e **escopo** (o que entra e o que fica fora);
- **arquivos** que serão tocados;
- **spec do que fazer** — o desenho da solução, no detalhe que a tarefa exigir;
- **critério de aceite** e **como validar** (quais gates);
- **nível da tarefa: simples · média · complexa**;
- **executor e revisor escolhidos**, com o **esforço** definido.

Tarefa pequena tem plano curto; tarefa complexa tem plano detalhado. O plano
vira arquivo em `specs/` quando o orquestrador julgar útil.

## Níveis e escolha do executor

O **nível** é definido pelo orquestrador no plano e determina quem executa —
preferindo sempre a **qualificação do agente para aquele tipo de trabalho**:

| Nível | Executores preferenciais |
| --- | --- |
| **Simples** — mudança local, texto, rótulo, ajuste isolado | Grok · opencode (DeepSeek v4 Pro) · Claude **Sonnet 5** · ChatGPT **Luna** |
| **Média** — feature pequena, refactor localizado | **Grok** · Claude **Sonnet 5** · ChatGPT **Terra** · opencode (DeepSeek v4 Pro) |
| **Complexa** — arquitetura, segurança, cálculo, multi-arquivo com risco | **Grok** · Claude **Opus 5** · ChatGPT **Terra** |

**Nível de esforço:** decidido pelo orquestrador, caso a caso.

## Escolha do revisor

Também pelo orquestrador, entre **Claude Code Opus 5** ou **ChatGPT Terra (ou
superior)**. O revisor **nunca é o agente que executou**.

## Gauntlet

O método **Gauntlet** (barra concreta + builder × crítico em rodadas) só é usado
**por escolha expressa do orquestrador**, declarada no plano. Fora disso, vale
o PREVC.

## Onde o trabalho roda

**Tudo no branch principal do repositório.** Sem worktree, sem branch por
tarefa, sem checkout paralelo.

## Piso inegociável

1. **Gates verdes com a saída literal** anexada (`70`) — vermelho é tarefa não
   concluída.
2. **O revisor não é quem executou.**
3. **NUNCAs e perguntar × agir** (`90`).
4. **Fatos protegidos** (`40`): nada de inventar fato, número, lei, alíquota ou
   índice — diante de lacuna, apontar a fonte.

## Princípios

- **Investigue antes de assumir.** Informação exclusiva do dono → pergunte;
  o resto → interpretação razoável, com a suposição registrada.
- **Solução proporcional ao problema**, sem over-engineering.
- **Não mexa em código não relacionado** — vira questão separada relatada.
- **Verificação com evidência:** relate a saída do gate, não a conclusão de que
  passou. Correção de defeito exige teste que reprova sem a correção.
- **Ritmo:** autonomia dentro da tarefa; concluída, reportar e puxar a próxima.
- Zero comentários por padrão no código; comentário só para o **porquê**
  não-óbvio, em uma linha.
