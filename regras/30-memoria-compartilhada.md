# 30 — Memória de trabalho compartilhada entre agentes [determinação do dono 2026-08-13]

> Fonte da verdade do **estado compartilhado por tarefa**. Permite que agentes de
> fornecedores diferentes (Claude, Codex, Gemini, Grok, opencode…), rodando em
> janelas/CLIs distintas sobre a mesma worktree, enxerguem o progresso uns dos
> outros. Complementa — não substitui — a SPEC (contrato) e o relatório
> (devolutiva).

## O arquivo de estado

**Só quando há 2+ agentes na tarefa** (`10`) — tarefa de agente único não precisa
de quadro-branco compartilhado: o relatório final é o registro. Nesses casos, o
**orquestrador cria**, junto com a SPEC:

```
_trabalho/ESTADO_<id-da-tarefa>.md
```

A pasta `_trabalho/` é **gitignorada** (contém `.gitignore` próprio com `*`):
estado é efêmero por natureza; o durável migra para SPEC/relatório/docs na
Confirmação. Como toda tarefa roda em worktree própria (`80`), o ESTADO vive
**dentro da worktree da tarefa** — todos os agentes da tarefa apontam para lá.

## Estrutura do ESTADO

```markdown
# ESTADO — <id> <título curto>
- **SPEC:** <caminho da SPEC>
- **Orquestrador:** <sessão/modelo>
- **Situação:** em planejamento | em execução | em validação | concluída

## Agentes ativos
| Agente | Fornecedor/modelo | Frente | Situação |

## Arquivos em edição (declarar ANTES de editar)
| Arquivo | Agente | Desde |

## Decisões tomadas durante a execução
- <data hora> — <decisão + 1 linha de motivo> (<agente>)

## Progresso por frente
- <frente>: <o que está feito, o que falta>

## Achados / questões separadas (fora do escopo — NÃO corrigir aqui)
- <descrição + arquivo>

## Pendências (inclusive do dono)
- <pendência + de quem depende>
```

## Protocolo

1. **Todo agente lê o ESTADO ao iniciar** e o atualiza **ao concluir cada etapa**
   relevante (não a cada edição de arquivo — alto sinal, baixo ruído).
2. **Declare o arquivo antes de editá-lo** na seção "Arquivos em edição" e
   remova a linha ao terminar. Arquivo já declarado por outro agente → não toque;
   registre a dependência em Pendências e avise o orquestrador.
3. Cada agente **edita apenas as próprias linhas**; nunca apagar ou reescrever
   registro alheio. Conflito de escrita no próprio ESTADO → o orquestrador
   resolve.
4. Decisão autônoma tomada durante a execução (interpretação de ambiguidade,
   escolha entre equivalentes) → registrada em "Decisões", com motivo.
5. **O orquestrador é o dono do ESTADO:** consolida, arbitra conflitos e, na
   Confirmação, **migra o durável** (decisões → SPEC/ADR; achados → questões
   separadas reportadas ao dono) e **apaga o arquivo**.
6. O ESTADO **não substitui** o relatório de devolução do executor (formato na
   SPEC) nem cria autorização — NUNCAs (`90`) e fatos protegidos (`40`) valem
   integralmente dentro dele.

## Por que assim

- Estado fora do git = zero poluição de histórico; o `git log` continua sendo o
  registro de atividade e a SPEC o registro da decisão.
- Arquivo por tarefa (e não um diário global) = morre com a tarefa, não apodrece.
- Declaração de arquivos em edição = previne a colisão clássica de executores
  paralelos na mesma worktree.
