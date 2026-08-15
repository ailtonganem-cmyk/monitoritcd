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
- **Escolhe a trilha da tarefa** (Direta | Padrão | Gauntlet — `10`) ao receber
  a demanda, e a registra em uma linha no despacho.
- **Limites de uso — orçamento por tarefa, não checagem por despacho** [v3]: ao
  abrir a tarefa, o orquestrador fixa o modelo preferido e o substituto de cada
  papel e **só reavalia se a quota estourar ou o agente falhar** — verificar
  antes de cada despacho é atrito sem ganho. Todos esgotados → registrar o
  bloqueio e aguardar a janela.

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
| Orquestrador (techlead) | Codex/ChatGPT | **GPT-5.6 Sol** (fixo) | **máximo** |
| Planejador/Crítico | Claude | **Fable 5** (`fable`) quando disponível | máximo / xhigh |
| Planejador/Crítico (fallback) | Claude / Codex | **Opus 5** (`opus`) ou **GPT-5.6 Sol** — só se Fable 5 indisponível | máximo / xhigh |
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

## Fluxo da tarefa — por trilha [dono 2026-08-14 v3]

A trilha (`10`) define quantos saltos a tarefa dá. **A separação de papéis é
estrita em todas elas** — o orquestrador nunca planeja nem codifica; o que muda
é quantos agentes a tarefa atravessa.

### Trilha Direta (padrão — o volume do dia a dia): 4 etapas

1. Dono encaminha a demanda ao **orquestrador**.
2. Orquestrador classifica a trilha e despacha **UM único agente** com o pedido
   e o **critério de aceite** — sem SPEC em arquivo.
3. Esse agente conduz **P + E + V** da tarefa inteira e devolve o resultado com
   a **saída literal dos gates**.
4. Orquestrador confere a evidência, **integra** (`80`), reporta e puxa a
   próxima tarefa.

*Sem cadeia planejador→executor→crítico: ela existe para isolar contexto e dar
perspectiva fresca — numa mudança local não há o que isolar.*

### Trilhas Padrão e Gauntlet (pipeline completo)

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
