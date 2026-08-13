# 20 — Orquestração e modelos por papel [determinação do dono 2026-08-13]

> Fonte da verdade de **quem pensa, quem codifica, com que modelo e esforço**.
> A regra é escrita por **PAPEL**; a tabela de mapeamento nome↔papel é o único
> lugar a atualizar quando um modelo novo é lançado.

## Papéis

### Orquestrador (modelo de pensamento)

Responsável por **todo** o planejamento, revisão, validação e **supervisão** dos
demais agentes: conduz P+R, escreve a SPEC de Execução, **lança os
agentes/subagentes executores**, acompanha o estado compartilhado (`30`),
valida com olhar independente e confirma. Também é o **único que usa git para
escrever** e o único que cria/integra worktrees (`80`).

- **Modelo:** o **mais forte disponível** do fornecedor escolhido, em esforço
  **máximo ou extra alto (xhigh)**.
- **Fornecedores habilitados como orquestrador:** Claude e ChatGPT.

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
| Orquestrador | Claude | **Fable 5** (`fable`) quando disponível; fallback **Opus 5** (`opus`) | máximo / xhigh |
| Orquestrador | ChatGPT | o mais forte disponível na conta | máximo / xhigh |
| Executor complexo | Claude | família **Opus** (`model: opus`) | xhigh / high |
| Executor complexo | ChatGPT | família de topo disponível | xhigh / high |
| Executor simples | Claude | família **Sonnet** (`model: sonnet`) | high / xhigh / max |
| Executor simples | ChatGPT | família intermediária/rápida | max |
| Executor simples | Grok / Gemini / opencode | o mais forte disponível | o mais alto disponível |

*Valores de `model` aceitos pela CLI do Claude Code: `fable`, `opus`, `sonnet`,
`haiku`. Nome de modelo de outro fornecedor é conferido no próprio fornecedor
antes de ser escrito aqui — esta tabela não registra modelo não verificado.*

*Fallback do orquestrador: indisponível o mais forte, cai para o intermediário
do mesmo fornecedor. A disciplina de papéis não muda no fallback.*

### Subagentes definidos neste repositório

| Arquivo | Papel | `model` |
| --- | --- | --- |
| `.claude/agents/executor-complexo.md` | Executor complexo | `opus` |
| `.claude/agents/executor-simples.md` | Executor simples | `sonnet` |

## Regras de despacho

1. **Proibido despachar executor sem SPEC ratificada** referenciada no prompt
   (`10`). Executor que receber despacho sem SPEC, ou com seção material vazia,
   **devolve ao orquestrador** — não improvisa.
2. **A escolha entre executor complexo e simples é do orquestrador**, caso a
   caso. Na dúvida, suba para o complexo: o custo de um refactor malfeito supera
   a diferença de modelo.
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
8. **MCPs indicados na SPEC** [dono 2026-08-13]: o orquestrador verifica na fase
   P se há MCP aplicável e a SPEC indica os MCPs/CLIs a utilizar (`10`,
   princípio 7). Executor que encontrar MCP indicado porém **não vinculado** ao
   seu agente devolve o bloqueio ao orquestrador, que conduz a vinculação com o
   dono (guiando o login; credenciais nunca passam pelo agente).

## Limites que a orquestração não dissolve

Nenhum consenso de agentes autoriza violar as NUNCAs (`90`) nem produz fato
normativo (`40`). Decisões de dinheiro, remoção de funcionalidade, ação
destrutiva em dados ou operação sobre dado real de terceiros são sempre do dono.
