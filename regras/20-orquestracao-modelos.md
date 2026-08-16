# 20 — Orquestração e modelos por papel [dono 2026-08-14 v2 — orquestrador fixo Codex Sol; planejador Fable 5; PREVALECE sobre disposições locais]

> Fonte da verdade de **quem gerencia, quem pensa, quem codifica, com que
> modelo e esforço**. A regra é escrita por **PAPEL**; a tabela de mapeamento
> nome↔papel é o único lugar a atualizar quando um modelo novo é lançado.

## Papéis

### Orquestrador — techlead (Codex — GPT-5.6 Sol, fixo) [dono 2026-08-14 v2]

**Gerência pura, sem produção de artefato técnico.** Função principal e
prioritária: **gerenciar e distribuir as tarefas entre os demais agentes**.
Recebe a demanda do dono, **verifica os limites de uso** dos agentes-alvo antes
de cada despacho, cria a worktree e o ESTADO da tarefa, **despacha o
planejador**, recebe de volta a SPEC com a classificação de complexidade,
**dispara executores e críticos**, acompanha o estado compartilhado (`30`),
integra (git — único que escreve e que cria/integra worktrees, `80`), confirma,
reporta e puxa a próxima tarefa (Gauntlet Loop). **Proibido ao orquestrador:
escrever SPEC, criar ou revisar código.** Ele confere que os gates rodaram e
que a evidência foi reportada — o julgamento técnico é do planejador/crítico.

- **Modelo:** Codex/ChatGPT **GPT-5.6 Sol**, em **esforço máximo**.
- **Despacha o planejador**, que escolhe o **método** (PREVC ou Gauntlet) e o tamanho do esforço no plano (`10`); o orquestrador não arbitra método.
- **Opera pela camada nativa do harness** (`25`): `run-create` → `task-create`
  (DAG) → `worker-start --agent --model --effort` → `check --wait` → gates →
  integração. Protocolo manual só para agente fora do harness.
- **Limites de uso — leitura no início da tarefa/ciclo** [v4]: consultar o
  medidor (`orca account list --json`) e aplicar o **roteamento por limiar**
  (`25`) — titular com uso semanal ≥ 85% cede ao substituto; ≥ 95% só com ordem
  do dono. **Não** reconsultar a cada despacho. O **roteamento efetivo** entra no
  relatório.

### Planejador / Crítico (modelo de pensamento)

Concentra o trabalho técnico de pensamento, **por despacho do orquestrador**:
conduz **P+R**, escreve a **SPEC de Execução** com **classificação de
complexidade obrigatória** (trivial | média | grande) — que vincula a escolha
do executor —, indica MCPs/CLIs e frentes, e **devolve ao orquestrador**. A
**crítica/validação** (V do PREVC e crítico do Gauntlet) é exercida por
**instância NOVA deste mesmo tier, com contexto limpo** — nunca quem
implementou, nunca crítico que viu rascunho anterior.

- **Modelo:** Claude **Fable 5** (o mais forte disponível), esforço **máximo
  ou extra alto (xhigh)**.
- **Fallback do planejador:** Fable 5 indisponível → **Opus 5** ou o próprio
  **Codex Sol**, à escolha do orquestrador conforme os limites disponíveis.

### Revisor do plano (R) [papel próprio desde v4]

Ataca o plano **antes** da execução: furos, riscos, conflito com `90`/`40`,
alternativa melhor. **Cruzamento:** de fornecedor diferente do planejador sempre
que houver disponibilidade. Ratifica a SPEC ou devolve com o motivo.

### Validador (V) [papel próprio desde v4]

Roda a matriz de validação (`70`) e emite o veredito **contra o critério de
aceite**, em **instância nova de contexto limpo** — nunca quem implementou;
**cruzado** com o executor. Evidência objetiva com saída literal **é** o
veredito; julgamento subjetivo vai contra a barra concreta.

### Executor complexo

Refactor amplo, arquitetura, segurança, regra de negócio crítica (`40`), parser
novo de fonte, mudança multi-arquivo com risco de regressão.

- **Modelo:** família de topo do fornecedor, esforço **extra alto ou alto**.

### Executor simples

Mudança local, texto/mensagem, ajuste de YAML de fonte, spec isolada, poda
mecânica.

- **Modelo:** família intermediária/rápida, no **maior esforço disponível**.

## Tabela de mapeamento nome↔papel (atualizável — editar SÓ aqui)

| Papel | Fornecedor | Modelo | Esforço |
| --- | --- | --- | --- |
| **Orquestrador** | Codex/ChatGPT | **GPT-5.6 Sol** · subst.: Fable 5 → Opus 5 | **máximo** |
| **Planejador (P)** | Claude | **Fable 5** (`fable`) · subst.: Opus 5 (`opus`) → Codex Sol | máximo / xhigh |
| **Revisor do plano (R)** | Codex / Gemini | **GPT-5.6 Sol** (cruzado com o planejador) · subst.: Gemini 3 Pro → Opus 5 | xhigh |
| **Validador (V)** | Claude / Gemini | **Opus 5** em contexto limpo (cruzado com o executor) · subst.: Gemini 3 Pro → Codex Sol | xhigh / máximo |
| Executor complexo | Claude | família **Opus** (`model: opus`) | xhigh / high |
| Executor complexo | ChatGPT | família de topo disponível | xhigh / high |
| Executor simples | Claude | família **Sonnet** (`model: sonnet`) | high / xhigh / max |
| Executor simples | ChatGPT | família intermediária/rápida | max |
| Executor simples | Grok / Gemini / opencode | o mais forte disponível (opencode: **disponível para codificação** — modelo decidido pelo orquestrador conforme a tarefa) | o mais alto disponível |

*Valores de `model` aceitos pela CLI do Claude Code: `fable`, `opus`, `sonnet`,
`haiku`. Nome de modelo de outro fornecedor é conferido no próprio fornecedor
antes de ser escrito aqui — esta tabela não registra modelo não verificado.*

*Fallbacks e interinidade [dono 2026-08-14 v2]: (a) **Orquestrador (Codex Sol)
indisponível** → o **Fable 5 assume interinamente a orquestração** daquela
tarefa, registrando no ESTADO e no relatório; o papel volta ao Codex Sol na
tarefa seguinte. (b) **Planejador (Fable 5) indisponível** → **Opus 5** ou o
próprio **Codex Sol** assume o planejamento, à escolha do orquestrador conforme
os limites. (c) Dentro de um papel, indisponível o mais forte → intermediário
do mesmo fornecedor. (d) **Acesso direto do dono** a um agente que não o
orquestrador vale como delegação: o agente acionado orquestra aquela demanda
interinamente, respeitando os papéis nos despachos. A disciplina de papéis não
muda em nenhum fallback.*

## Fluxo da tarefa — o plano decide o tamanho [v5]

**A separação de papéis é estrita** — o orquestrador nunca planeja nem codifica —
mas **quantos agentes a tarefa atravessa é decisão do plano** (`10`).

### Caso comum: um agente conduz a tarefa

1. Dono encaminha a demanda ao **orquestrador**.
2. Orquestrador despacha **UM único agente** com o pedido
   e o **critério de aceite** — sem SPEC em arquivo.
3. Esse agente conduz **P + E + V** da tarefa inteira e devolve o resultado com
   a **saída literal dos gates**.
4. Orquestrador confere a evidência, **integra** (`80`), reporta e puxa a
   próxima tarefa.

*Sem cadeia planejador→executor→crítico: ela existe para isolar contexto e dar
perspectiva fresca — numa mudança local não há o que isolar.*

### Quando o plano pede papéis separados

1. Dono encaminha a demanda ao **orquestrador** (Codex — GPT-5.6 Sol, esforço
   máximo).
2. Orquestrador **verifica limites de uso** e despacha a demanda ao
   **planejador**.
3. Planejador conduz P+R e devolve a **SPEC** com a classificação de
   complexidade, MCPs e frentes.
4. Orquestrador **dispara os executores** conforme a complexidade indicada e
   acompanha pelo ESTADO (`30`).
5. Concluída a execução, o orquestrador **dispara o crítico** (instância nova
   do tier planejador, contexto limpo) — loop builder×crítico até a barra
   (`10`, Gauntlet).
6. Aprovado, o orquestrador **integra** (git/merge — `80`), confirma, reporta
   ao dono e puxa a próxima tarefa da fila.

### Subagentes definidos neste repositório

| Arquivo | Papel | `model` |
| --- | --- | --- |
| `.claude/agents/executor-complexo.md` | Executor complexo | `opus` |
| `.claude/agents/executor-simples.md` | Executor simples | `sonnet` |

## Regras de despacho

1. **Proibido despachar executor sem SPEC ratificada** referenciada no prompt
   (`10`). Executor que receber despacho sem SPEC, ou com seção material vazia,
   **devolve ao orquestrador** — não improvisa.
2. **A complexidade vem da SPEC** (classificada pelo planejador); o
   orquestrador escolhe o fornecedor conforme a tabela e os **limites de uso**.
   Na dúvida, o planejador classifica para cima: o custo de um refactor
   malfeito supera a diferença de modelo.
3. Ao delegar codificação por ferramenta de subagente, passar o **modelo
   explicitamente** — agente lançado sem o parâmetro herda o modelo da sessão e
   viola esta regra.
4. Agentes de **investigação, revisão e colegiado** (read-only) rodam no mais
   forte, herdando o modelo da sessão de pensamento.
5. **Divisão por frente** (coleta / classificação / notificação / testes) é **a
   critério do orquestrador**: frentes com arquivos disjuntos rodam em paralelo;
   frentes que tocam os mesmos arquivos ou exigem sequência cirúrgica rodam em
   série.
6. **Executores de outros fornecedores** (ChatGPT/Codex, Grok, Gemini, opencode)
   rodam em **janela/CLI/instância própria**, fora da sessão do orquestrador. A
   supervisão se dá **por arquivos**: SPEC na ida, estado compartilhado (`30`)
   durante, relatório na volta. Integração, validação e git permanecem
   exclusivos do orquestrador.
7. Paralelizar só quando houver ganho real; tarefa trivial não justifica agente.
8. **MCPs indicados na SPEC** [dono 2026-08-13; papel ajustado 2026-08-14]: o
   **planejador** verifica na fase P se há MCP aplicável e a SPEC indica os
   MCPs/CLIs a utilizar (`10`, princípio 7); o **orquestrador** confere a
   vinculação e os limites antes do despacho. Executor que encontrar MCP
   indicado porém **não vinculado** ao seu agente devolve o bloqueio ao
   orquestrador, que conduz a vinculação com o dono (guiando o login;
   credenciais nunca passam pelo agente).

## Limites que a orquestração não dissolve

Nenhum consenso de agentes autoriza violar as NUNCAs (`90`) nem produz fato
normativo (`40`). Decisões de dinheiro, remoção de funcionalidade, ação
destrutiva em dados ou operação sobre dado real de terceiros são sempre do dono.
