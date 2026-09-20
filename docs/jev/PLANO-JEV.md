# Plano de implementação do Jev no MonitorITCD

Data: 2026-09-20. Autor: sessão Orca `jev-ia-inventario-20260920`.
Base: [`../JEV-IA-INVENTARIO.md`](../JEV-IA-INVENTARIO.md) · Estado atual:
[`CALLPOINT-MONITORITCD.md`](CALLPOINT-MONITORITCD.md).

Objetivo: levar o Jev a **todo** ponto do MonitorITCD onde existe um fork material —
começando por observar, e só promovendo a bloqueio o que tiver divergência medida e explicada.

## Invariantes do plano

1. **Jev indisponível não para o trabalho.** Sem veredito, a rotina segue como se o Jev não
   existisse. No código: `DecisaoJev.bloqueia`, verdadeiro só num `deny` explícito recebido.
   Exceção única: o gate de produção nunca autoriza por omissão.
2. Jev arbitra forks tipados; não escreve conteúdo de produto.
3. Perguntas em inglês, prosa em pt-BR.
4. Nenhum gate substitui validação existente (pydantic, allowlist de tópicos, Rules, authn).
5. Deny nunca descarta item coletado em silêncio — rebaixa, adia ou recusa entrada.
6. Nada de yolo, skip-permissions ou force-push a partir de um score.
7. Cada fase fecha com os comandos canônicos do `AGENTS.md`: `pytest` (cobertura ≥ 95),
   `ruff check .`, `ruff format --check .`, `mypy` — todos exit 0.

## Estado por fase

| Fase | Escopo | Gates | Risco | Estado |
|---|---|---|---|---|
| 0 | Shadow em todos os callpoints viáveis | `citation`, `critico`, `material`, `destructive`, `guardrails` | R1 | **feito** |
| 1 | `citation` e `guardrails` em Act | 2 | R1 | pendente |
| 2 | `critico` e `destructive` em Act | 2 | R1 | pendente |
| 3 | `material` (rota e painel) em Act advisory | 2 | R1 | pendente |
| 4 | `producao` nos workflows que injetam chave de IA | 1 | **R2** | pendente |
| 5 | `judge` no eval de prompt | 1 | R0/R1 | pendente |
| 6 | Cobertura ampliada: notificação, dedup, coleta | a definir | R1 | proposta |

## Fase 0 — shadow (feito)

Seis callpoints instrumentados, nenhum alterando o fluxo. Detalhe operacional, variáveis de
ambiente e como ler os logs: `CALLPOINT-MONITORITCD.md`.

Entregue: `src/monitoritcd/llm/jev_gate.py`, `docs/jev/gates/*.yaml`, callpoints em
`orchestrator.py`, `bot/handlers.py` e `painel/ia_provedores.py`, mais 43 testes.

## Fase 1 — `citation` e `guardrails` em Act

**Pré-requisito:** pelo menos duas semanas de shadow em execução real, com amostragem manual
de 20 denies por gate. Promover só o que tiver causa identificada.

`citation` (saída do classificador):

- deny → o item **não** é descartado. Recebe `severity_tier` rebaixado para o digest e um campo
  de motivo persistido junto do documento, para revisão do dono.
- O rebaixamento precisa de campo novo no `LLMResult` ou em `metadados_extraidos`. Decidir qual
  antes de codar — mexer no schema persistido é o que torna esta fase R1 e não R0.
- Jev indisponível → item segue pelo caminho normal, sem rebaixar nada.

`guardrails` (descrição de tópico em `/topicos`):

- deny → o comando recusa a descrição com mensagem explicando o motivo; o tópico não é criado.
- Jev indisponível → o tópico é criado normalmente. A defesa que já existe (`_prompt_data_literal`
  mais a regra 8 do prompt) continua valendo sozinha, como vale hoje.

Testes obrigatórios: allow, deny e indisponível, para cada um dos dois caminhos.

## Fase 2 — `critico` e `destructive` em Act

`critico`: deny (`digest_only` ou `need_more_evidence`) desvia o item do push imediato para o
digest. Vale só para a rota de notificação — a classificação armazenada não muda.

`destructive`: deny antes de `/reprocessar` emitir o token de confirmação. A mensagem devolve o
motivo tipado ao dono, que pode reexecutar com janela menor. Jev indisponível → confirmação
segue pelo fluxo de dois passos que já existe.

## Fase 3 — `material` advisory

`rota-provedor`: a escolha continua sendo a cadeia do painel. O Jev entra como sugestão
registrada, e a promoção a efetivo exige antes que o campo `esforco` do painel deixe de ser
metadado morto (ver Pendências). Enquanto `esforco` não for lido, não há o que rotear.

`cadeia-painel`: deny impede persistir uma cadeia que deixaria o projeto sem provedor utilizável.
A validação estrutural de `gravar` já cobre família e modelo; o Jev cobre o que ela não vê —
cadeia vazia de fato, fallback removido sem substituto.

## Fase 4 — `producao` (R2)

Os workflows `monitor.yml`, `digests.yml`, `reprocess.yml` e `deploy-functions.yml` injetam chave
de IA em execução real. O gate de fim limpo (`templates/producao-fim-limpo.yaml` da frota) entra
antes do passo que publica.

Toca CI e release: gatilho R2 declarado no `AGENTS.md` local. Exige plano curto com aceite dito,
revisão independente e pedido expresso do founder. **Nenhuma sessão deve fazer isto sem essa
autorização.** Neste gate, e só neste, ausência de veredito não libera produção.

## Fase 5 — `judge` no eval de prompt

Rubrica tipada junto do snapshot de `PROMPT_VERSION`, para que um bump de versão traga evidência
de qualidade e não só a quebra do snapshot. Roda em CI ou local, nunca no caminho de produção.

## Fase 6 — cobertura ampliada (proposta)

Pontos onde existe fork material e hoje não há gate nenhum. Levantados, não priorizados:

- **Notificação**: `notify_documents` decide canal e urgência por tier. Um `confidence-routing`
  poderia separar "manda agora" de "espera o digest" em item de fronteira.
- **Dedup e cluster**: `assign_clusters` agrupa por similaridade textual (difflib). Um `noul`
  de "mesmo ato?" resolveria os casos que a similaridade erra entre UFs.
- **Saúde de fonte**: `source_run_health` alerta fonte com zero itens. Um `choice` separaria
  "fonte quebrada" de "dia sem publicação".
- **Coleta**: seleção de fontes por execução, hoje estática.

Nenhum desses é urgente. Entram depois que as fases 1–3 estiverem calibradas, e cada um exige
o mesmo ciclo: shadow primeiro, Act depois.

## Fora de alcance permanente

- Jev não gera nem revisa conteúdo jurídico. Não opina sobre mérito de ato, alíquota ou decisão.
- Jev não altera `original.*` — dado coletado é write-once.
- Jev não toca Rules, IAM nem Functions.
- Jev não substitui autorização humana onde o `AGENTS.md` já exige pedido expresso.

## Pendências herdadas do inventário

- O campo `esforco` do painel é persistido e nunca lido por `montar_cadeia`. Bloqueia a Fase 3.
- `OPENCODE_API_KEY` está declarada em `config.py` e no `.env.example` sem adaptador em
  `_instanciar`. Decidir entre implementar ou remover.
- O `.venv` do worktree aponta para o repo principal, então a suíte precisa de `PYTHONPATH=src`
  para testar o código do worktree. Confirmar se o CI sofre do mesmo problema.
