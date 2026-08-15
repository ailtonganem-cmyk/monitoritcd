# 10 — Método de trabalho: PREVC, SPEC de Execução, verificação, GSD

> Fonte da verdade do **como se trabalha**. Vale para todo agente, de qualquer
> fornecedor.

## Trilhas de trabalho — o esforço é proporcional ao risco [dono 2026-08-14 v3]

> **Correção de rumo:** exigir o pipeline completo em toda tarefa trava o
> processo. A régua é **risco × reversibilidade**, não formalidade uniforme.
> Fundamento: a própria Anthropic documenta a cadeia
> `planejador → executor → testador` como anti-padrão ("telefone sem fio") fora
> dos casos em que isolamento de contexto, paralelismo ou perspectiva fresca
> realmente compensam.

| Trilha | Quando | Como roda |
| --- | --- | --- |
| **Direta** (**padrão**) | Mudança local, texto/mensagem, ajuste de YAML de fonte, doc, poda mecânica, bugfix pequeno com teste | O orquestrador despacha **UM único agente**, que conduz **P + E + V da tarefa inteira** — sem subdividir em planejador/executor/crítico. Validação = **gates objetivos + evidência**. Sem SPEC em arquivo, sem crítico separado. |
| **Padrão** | Feature pequena/média, refactor localizado, decisão técnica reversível | P+R pelo planejador (**SPEC-lite**, 5 campos), execução por executor, **crítico separado na entrega**. |
| **Gauntlet** | Alto risco: arquitetura, segurança, regra de negócio crítica (`40`), parser novo de fonte, dado de produção | Pipeline completo — decomposição em partes julgáveis, **builder × crítico de contexto limpo** por parte, barra concreta com exemplar, SPEC formal, worktree. |

- **Quem escolhe:** o orquestrador, ao receber a demanda; o dono pode fixar a
  trilha a qualquer momento.
- **Subir de trilha é livre e esperado:** qualquer agente que encontre risco não
  previsto **para e sobe a tarefa de trilha**, registrando o motivo. **Descer de
  trilha exige ordem do dono.**
- **Limiar de fan-out:** só vale dividir entre agentes quando há **3+ frentes
  independentes** de porte relevante. Abaixo disso, um agente só é mais rápido
  fim a fim — cada handoff custa contexto duplicado e perda de sinal.
- **Lote de triviais:** tarefas triviais correlatas podem ser agrupadas em **um
  único lote** que percorre o ciclo uma vez, com evidência por item.

## Ciclo obrigatório — PREVC

Toda tarefa passa por **P**lanejamento → **R**evisão do plano → **E**xecução →
**V**alidação → **C**onfirmação, em dois blocos. **O ciclo é universal; o que
escala com a trilha é a formalidade de cada etapa.**

### Bloco 1 — Especificação (P + R), ANTES de tocar em código

1. **P — Planejamento:** entender o problema, mapear arquivos/dependências,
   levantar opções, definir **critério de aceite** e **plano de validação**.
2. **R — Revisão do PLANO (não do código):** ataque adversarial ao plano —
   furos, riscos, conflito com as NUNCAs (`90`), alternativa melhor.
   **Saída obrigatória: a SPEC de Execução ratificada, por escrito.**

### SPEC de Execução — o Bloco 1 termina em DOCUMENTO, não em raciocínio

O agente que **pensa** é o que **documenta**: arquitetura, system design,
métodos e melhores práticas do caso concreto são registrados por escrito ANTES
de qualquer edição. A SPEC é a **única entrada autorizada** de um agente de
codificação (regra de despacho no módulo `20`).

- Trilha **Direta** → **sem SPEC**: o pedido + o critério de aceite em uma linha
  bastam. Gatilho: *escreva a SPEC se você ficaria insatisfeito com o agente
  interpretando o pedido de outro jeito; se um follow-up rápido corrigiria o
  resultado, não escreva.*
- Trilha **Padrão** → **SPEC-lite** no próprio despacho, **5 campos**: objetivo ·
  arquivos · critério de aceite · plano de validação · riscos e limites.
- Trilha **Gauntlet** → arquivo `specs/SPEC_<ID>_<slug>.md` com as seções:
  identificação · problema e objetivo · escopo (dentro/fora) · mapa de arquivos ·
  system design · decisões e alternativas descartadas · métodos e melhores
  práticas obrigatórias · plano de execução · riscos e armadilhas · critério de
  aceite · plano de validação · evidência exigida · registro do R.
  Modelo pronto: `specs/_TEMPLATE_SPEC.md`.
- **A SPEC é versionada no git** [decisão do dono 2026-08-13] e entra no commit
  da tarefa — é o registro durável do *porquê*, que o `git log` não captura.
- A SPEC **classifica a complexidade** (trivial | média | grande) — campo
  obrigatório que vincula a escolha do executor pelo orquestrador (`20`).
- **Limite duro:** a SPEC não cria fato — nenhuma seção autoriza arbitrar dado
  normativo (`40`/`90`); diante de lacuna, aponta a fonte a consultar.

### Bloco 2 — Realização (E → V → correção → C), em loop até apto

3. **E — Execução:** implementar conforme a SPEC (GSD, segurança, convenções do
   repositório; sem over-engineering). Executor não replaneja nem expande escopo.
4. **V — Validação:** rodar os gates objetivos do módulo `70` + julgamento de
   qualidade. **V vermelho = tarefa não concluída.** Falhou → diagnosticar
   causa-raiz: bug de execução volta a E; erro de concepção volta ao Bloco 1.
   **Anti-loop: até 3 rodadas E↔V; persistindo → reavaliar a SPEC; falhando
   ainda → escalar ao dono.**
5. **C — Confirmação:** só com V plenamente verde. Deploy quando aplicável +
   smoke + evidência anexada + persistir só o durável (`80`).

## Escala por risco/tamanho (GSD) — equivale às trilhas

- **Trivial → trilha Direta:** um agente conduz P+E+V; validação por gate focal
  do que foi tocado + evidência; sem SPEC em arquivo, sem crítico separado.
- **Média (5–10 arquivos) → trilha Padrão:** SPEC-lite; crítico separado na
  entrega; olhar independente na V.
- **Grande (arquitetura, produção, segurança, dados) → trilha Gauntlet:** SPEC
  formal + ADR em `docs/adr/` quando a decisão for arquitetural; V reforçada.

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

## Gauntlet Loop — método do ritmo contínuo [dono 2026-08-14]

Método de iteração multi-agente **builder × crítico** (popularizado por Matt
Shumer), aplicado em duas camadas:

1. **Entre tarefas — loop contínuo:** a fila é percorrida em loop; cada tarefa
   atravessa o PREVC completo e, confirmada, o orquestrador **reporta e inicia
   imediatamente a próxima**, na ordem da fila.
2. **Dentro da tarefa — estrutura do E↔V:**
   - o **planejador** decompõe o objetivo nas **menores partes julgáveis
     separadamente** (o orquestrador despacha e acompanha — `20`);
   - cada parte tem um **builder** (executor) e um **crítico separado, com
     contexto limpo** — quem implementa **nunca** julga o próprio trabalho;
   - a **barra de qualidade é definida ANTES e é concreta**: critérios
     objetivos + **exemplar de referência** comparado **lado a lado** com o
     resultado — nunca "faça excelente";
   - reprovado → o crítico aponta **o maior gap remanescente** e devolve ao
     builder; **crítico que viu rascunho anterior não julga o retry** — crítico
     de contexto novo a cada rodada;
   - aprovado na barra → segue para a Confirmação do PREVC.

### Quando o loop builder × crítico vale a pena [v3]

- **A camada 1 (loop entre tarefas) vale em TODAS as trilhas; a camada 2
  (builder × crítico) é da trilha Gauntlet** — opcional na Padrão, dispensada na
  Direta.
- **Gauntlet é segunda passada, não primeiro rascunho** — assim é no método
  original: a primeira versão sai pela trilha Direta ou Padrão e o loop entra
  para **afinar** contra a referência concreta. Usá-lo para produzir rascunho é
  o uso mais caro e menos eficaz da técnica.
- **Crítico dosado:** obrigatório onde o julgamento é **subjetivo** (UI,
  microcopy, arquitetura, regra de negócio); onde a evidência é **objetiva**
  (tipos, lint, testes, build, smoke), o **gate verde com saída literal É a
  validação** — crítico adicional ali é cerimônia sem ganho.
- **Stopping condition definida ANTES do run:** máximo de **3 rodadas** E↔V e,
  em execuções longas, também um teto de tempo.

O anti-loop do PREVC permanece (3 rodadas E↔V sem convergir → escalar ao dono)
e o loop **não dissolve** as NUNCAs nem a tabela perguntar × agir (`90`).

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
