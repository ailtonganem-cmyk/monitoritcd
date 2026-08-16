# 10 — Método de trabalho [v5 — o plano manda]

> Fonte da verdade do **como se trabalha**. Vale para todo agente, de qualquer
> fornecedor.

## ★ Regra de ouro — o PLANO manda ★ [2026-08-16 v5]

**O que não estiver no plano não é exigido.** Este módulo define o **piso**
(curto e inegociável) e o **cardápio** de que o planejador dispõe; fora do piso,
cerimônia entra quando o plano a coloca, e só então.

> **v5 revoga** a taxonomia de trilhas (Direta/Padrão/Gauntlet), as três camadas
> do Gauntlet, o gate de fila formal e a SPEC de 13 seções obrigatória — viraram
> classificações sobrepostas que travaram a entrega.

### O plano de trabalho — cinco campos

Objetivo · arquivos prováveis · **critério de aceite** · como validar · **método**.

Cabe **no próprio despacho**; vira arquivo só quando o planejador julgar útil
(risco alto, várias frentes, retomada futura). Pode declarar explicitamente o
que **não** será feito ("sem crítico separado", "sem worktree", "sem ADR").
Gatilho para detalhar mais: *escreveria mais se ficasse insatisfeito com o
agente interpretando o pedido de outro jeito*.

### Os dois métodos — escolha do planejador

| Método | Como funciona | Quando escolher |
| --- | --- | --- |
| **PREVC** (padrão) | Planejar → Revisar o plano → Executar → Validar → Confirmar. Linear, uma passada. | O alvo é claro e o certo se conhece de antemão: correção, refactor, regra objetiva, infraestrutura. |
| **Gauntlet** | Barra concreta declarada **antes** (critérios + exemplar) → builder produz → **crítico de contexto limpo** julga → repete apontando o **maior gap** até passar. | Qualidade subjetiva ou comparativa: UI, microcopy, texto institucional, acabamento — quando a primeira versão não tem como estar certa. |

**São alternativas, não camadas:** o Gauntlet **substitui** o PREVC quando o
planejador entender que rende mais, e a escolha fica registrada no plano. Podem
ser combinados por parte da tarefa. A **revisão do plano** só é obrigatória
quando o plano toca segurança, dado real, cálculo ou produção; fora disso o
planejador auto-revisa e segue.

### Piso inegociável — vale mesmo no plano mais enxuto

1. **Gates objetivos verdes**, com **saída literal** anexada. Vermelho é tarefa
   não concluída.
2. **Quem escreveu não valida a própria entrega** — contexto limpo, cruzado de
   fornecedor quando houver folga.
3. **NUNCAs e perguntar × agir** (`90`); **fatos protegidos** (`40`).
4. **Anti-loop:** 3 rodadas sem convergir → escalar com o gap nomeado.

**Tarefa pequena não paga pedágio:** plano, execução e gates cabem num **único
agente**; dividir entre agentes só compensa com **três ou mais frentes
independentes**.


## Ciclo obrigatório — PREVC

Toda tarefa passa por **P**lanejamento → **R**evisão do plano → **E**xecução →
**V**alidação → **C**onfirmação, em dois blocos. **O ciclo é universal; o que
escala é a formalidade de cada etapa, conforme o plano.**

### Bloco 1 — Especificação (P + R), ANTES de tocar em código

1. **P — Planejamento:** entender o problema, mapear arquivos/dependências,
   levantar opções, definir **critério de aceite** e **plano de validação**.
2. **R — Revisão do PLANO (não do código):** ataque adversarial ao plano —
   furos, riscos, conflito com as NUNCAs (`90`), alternativa melhor.
   **Saída: o plano de trabalho de 5 campos.** Revisão do plano só é obrigatória em risco — segurança, dado real, cálculo ou produção.

### Bloco 2 — Realização (E → V → correção → C), em loop até apto

3. **E — Execução:** implementar conforme o plano (GSD, segurança, convenções do
   repositório; sem over-engineering). Executor não replaneja nem expande escopo.
4. **V — Validação:** rodar os gates objetivos do módulo `70` + julgamento de
   qualidade. **V vermelho = tarefa não concluída.** Falhou → diagnosticar
   causa-raiz: bug de execução volta a E; erro de concepção volta ao Bloco 1.
   **Anti-loop: até 3 rodadas E↔V; persistindo → reavaliar o plano; falhando
   ainda → escalar ao dono.**
5. **C — Confirmação:** só com V plenamente verde. Deploy quando aplicável +
   smoke + evidência anexada + persistir só o durável (`80`).

## Ritmo — autonomia dentro da tarefa, loop contínuo entre tarefas

[decisão do dono 2026-08-14 — **Gauntlet Loop substitui** a "parada entre
tarefas" de 2026-08-13]

- **Autonomia vale DENTRO da tarefa:** conduzir sem interrupção até a conclusão
  (PREVC completo); não pausar por bloqueio percebido — fazer o preparatório
  possível e explicitar a pendência no chat. A "regra de execução autônoma" do
  projeto (`00`) opera aqui: instalar, configurar, commitar, deployar e disparar
  workflow são livres dentro da tarefa, com gates verdes.
- **Entre tarefas HÁ loop — Gauntlet Loop:** concluída e confirmada a tarefa,
  **reportar com evidência e prosseguir imediatamente à próxima** na ordem da
  fila, até esgotá-la ou haver ordem de parada. Ver "Gauntlet Loop" abaixo.
- Questionamento técnico razoável sem resposta em **60 s** → considerar
  autorizado e prosseguir (anunciar). Não vale para itens da tabela
  perguntar × agir (`90`) nem para informação exclusiva do dono.

## Princípios de trabalho

1. **Investigue antes de assumir.** Escolha material/arriscada ou informação
   exclusiva do dono → pergunte; caso contrário, escolha a interpretação
   razoável, prossiga e **registre a suposição**.
2. **Solução proporcional ao problema.** Regra de 3 antes de abstrair; sem
   flexibilidade ainda não necessária; sem half-finished.
3. **Não mexa em código não relacionado.** Problema descoberto fora do escopo é
   **questão separada** relatada, nunca correção silenciosa.
4. **Marque a incerteza explicitamente.** Confiança sem certeza causa mais dano
   que admitir lacuna.
5. **Aberto a ideias melhores** — sugira a abordagem de impacto duradouro.
6. **Opções para o dono = formato de seleção** (ferramenta de pergunta com
   opções marcáveis; recomendação em 1º com "(Recomendado)"), nunca prosa que o
   obrigue a redigir resposta.
7. **MCP primeiro, havendo possibilidade técnica** [dono 2026-08-13]: em toda
   tarefa, inventariar as CLIs/MCPs/superfícies aplicáveis; **existindo MCP
   tecnicamente capaz de resolver a tarefa, ele DEVE ser utilizado** — o
   **planejador** verifica na fase P e **indica na SPEC qual MCP usar** (o
   orquestrador confere vinculação e limites antes do despacho — `20`). Se a
   ferramenta MCP existir mas ainda não estiver **vinculada/autenticada**,
   **solicitar a vinculação ao dono, guiando-o passo a passo no login** — a
   autenticação é sempre dele (credenciais, códigos e tokens nunca passam pelo
   agente). Enquanto não vinculado, usar a alternativa canônica segura e
   registrar o bloqueio. Neste projeto, MCPs mais prováveis: Firebase (Firestore,
   rules, functions, logs) e Chrome DevTools (diagnóstico de fonte que quebrou).

## Verificação — "como você me confirma que isso está correto?"

Toda tarefa carrega essa pergunta implícita do dono. Antes de executar,
**descreva como vai executar**; depois, **verifique ativamente** (gates + prova
empírica: reproduzir, medir, rodar `--dry-run`, conferir o documento gravado) e
**relate a evidência** — saída literal —, não apenas a conclusão.

## Código auto-documentado

Zero comentários por padrão; comentário só para o **porquê** não-óbvio, em uma
linha — com uma exceção do domínio: **decisão de domínio vira comentário**
(ex.: "esta UF publica alíquota progressiva em anexo separado, exige parsing
próprio"). Jamais comentário WHAT, sobre callers, ou docstring multi-parágrafo.
Espelhe o padrão existente do repositório antes de inventar desenho novo.

**Idioma no código** (`AGENTS.md`/`CLAUDE.md`): comentários e docstrings em
pt-BR; **identificadores em inglês** (variáveis, funções, classes, módulos),
exceto termos jurídicos sem tradução fiel — `causa_mortis`, `espolio`,
`inventario`, `doacao`.
