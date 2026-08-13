# MonitorITCD — CLAUDE.md (hub) [v2 — 2026-08-13]

> Hub de regras lido pelo Claude Code. **A fonte da verdade são os módulos em
> `regras/`** — este arquivo é o índice e o resumo do que é inegociável. O
> `AGENTS.md` é o hub gêmeo no padrão aberto, lido pelos demais agentes (Codex,
> Gemini CLI, Grok, opencode, Cursor…); em divergência entre hubs, **vale o
> módulo**. Regras específicas do Claude Code (memória, subagentes) vivem só aqui.

## ★ Precedência dentro deste repositório ★

Dentro de `C:\Projetos\MonitorITCD` valem **este hub e os módulos `regras/`**,
que **prevalecem sobre qualquer `CLAUDE.md` de diretório ancestral** (incluindo
`C:\Projetos\CLAUDE.md`, que pertence a outro projeto e é carregado apenas por
ser diretório pai). Regra do ancestral que conflite com um módulo daqui —
metodologia, ritmo de trabalho, design system, painel de agentes — **não se
aplica ao MonitorITCD**.

## ★ Regras prioritárias auto-aplicadas ★

- **(a) Idioma — SOMENTE pt-BR.** Chat, commits, PR, SPECs, ADRs, runbooks,
  comentários, docstrings e mensagens ao dono: sempre e somente português
  brasileiro, com ortografia rigorosa — mesmo com input em inglês.
  **Identificadores de código permanecem em inglês** (exceto termos jurídicos
  sem tradução fiel: `causa_mortis`, `espolio`).
- **(b) Modo bypass — sem prompts em rotina técnica.** A segurança vem da defesa
  em profundidade (hooks + `permissions.deny` + pre-commit + NUNCAs), não de
  prompts. O bypass não elimina o juízo do `90` — nessas hipóteses, parar e
  **perguntar no chat**.

## §0 — Ciclo obrigatório PREVC (resumo)

Toda tarefa: **P**lanejamento → **R**evisão do plano → **E**xecução →
**V**alidação → **C**onfirmação. O Bloco 1 (P+R) termina em **SPEC de Execução
escrita** — única entrada autorizada de agentes de codificação; tarefa
média/grande tem SPEC versionada em `specs/`. V vermelho = tarefa não concluída;
até 3 rodadas E↔V, depois escalar ao dono.
**Detalhe integral:** `regras/10-metodo-trabalho.md`.

## Ritmo — autonomia dentro da tarefa, parada entre tarefas

Conduzir a tarefa inteira sem interrupção (a regra de execução autônoma do
projeto autoriza instalar, configurar, commitar, deployar e disparar workflow —
`regras/00-identidade-projeto.md`). **Concluída a tarefa: reportar com evidência e aguardar
determinação do dono.** Não há loop entre tarefas, não há wakeup reagendado, não
se puxa o próximo item por conta própria [decisão do dono 2026-08-13].

## Orquestração de modelos (resumo)

Pensar no papel **Orquestrador** (modelo mais forte disponível, esforço máximo);
codificar por complexidade em **Executor complexo** (`opus`) e **Executor
simples** (`sonnet`), sempre com `model` explícito e SPEC referenciada.
Detalhe: `regras/20-orquestracao-modelos.md`. Estado compartilhado entre agentes:
`regras/30-memoria-compartilhada.md`.

## Worktree por tarefa (resumo)

**Toda tarefa — inclusive trivial — é realizada em worktree git própria**
(`../MonitorITCD-worktrees/<id>`), criada e integrada pelo orquestrador; a
árvore principal nunca recebe edição direta. Worktree não herda `.venv` nem
gitignorados — recriar o venv e copiar o que está em `.worktreeinclude`.
Fluxo completo: `regras/80-git-e-entrega.md`.

## §4.5 — NUNCAs (resumo inegociável)

- NUNCA inventar fato, número, lei, alíquota, prazo ou jurisprudência — nem no
  texto do agente, nem no que o LLM do pipeline gera. Em dúvida, apontar a fonte.
- NUNCA alterar conteúdo coletado: `original` é write-once.
- NUNCA hardcodar secrets; NUNCA confiar na entrada (inclusive a do dono).
- NUNCA `git add .` em repo sujo; NUNCA `--no-verify` sem motivo documentado.
- NUNCA criar contas, autorizar pagamentos ou aceitar termos sem confirmação.
- NUNCA apagar dados de produção em massa sem ordem expressa.
- NUNCA concluir com gate vermelho.
- Lista completa e anti-padrões: `regras/90-seguranca-limites.md`.

## §9 — Perguntar × agir (resumo)

**Decidir e anunciar:** escolhas técnicas dentro da tarefa; commit, push,
workflow e deploy de function com gates verdes.
**Perguntar sempre:** dinheiro/billing, termos, delete ou escrita em massa em
produção, `push --force`, ativação/desativação de UF, mudança de severity tier
ou de provedor de LLM, dado real de terceiros, projeto fora deste repositório.
Tabela completa: `regras/90-seguranca-limites.md`.

## Índice — fonte da verdade

| Assunto | Módulo |
| --- | --- |
| Identidade, pessoas, IDs, stack, execução autônoma | `regras/00-identidade-projeto.md` |
| Método de trabalho (PREVC, SPEC, verificação, GSD) | `regras/10-metodo-trabalho.md` |
| Orquestração e modelos por papel | `regras/20-orquestracao-modelos.md` |
| Memória compartilhada entre agentes | `regras/30-memoria-compartilhada.md` |
| Regras de negócio: domínio, fatos protegidos, LLM, UFs | `regras/40-regras-negocio.md` |
| Saídas: e-mail, Telegram, bot | `regras/50-saidas-notificacoes.md` |
| Backend: segurança, limites, secrets, persistência | `regras/60-backend.md` |
| Testes, gates e armadilhas conhecidas | `regras/70-testes-validacao.md` |
| Git, worktree, entrega e documentação (DoD) | `regras/80-git-e-entrega.md` |
| Segurança, NUNCAs e limites | `regras/90-seguranca-limites.md` |

**Consulte o módulo ANTES de agir no assunto correspondente** — o hub resume; o
módulo decide. Conhecimento técnico durável (arquitetura C4, STRIDE, runbooks,
ADRs, situação das fontes por UF) vive em `docs/`, referenciado pelos módulos.

## Específico do Claude Code

- **Memória persistente:** `~/.claude/projects/C--Projetos-MonitorITCD/memory/` —
  point-in-time, pode ficar stale; verificar a realidade antes de agir com base
  nela.
- **Subagentes:** `.claude/agents/executor-complexo.md` (`opus`) e
  `.claude/agents/executor-simples.md` (`sonnet`). Despacho **sempre** com
  `model` explícito e SPEC referenciada (`regras/20-orquestracao-modelos.md`).
- **Promoção:** regra recorrente (≥ 2 sessões), universal e cara de violar →
  promover da memória para o módulo `regras/` correspondente.

---

*Em caso de conflito: módulo `regras/` > este hub > qualquer `CLAUDE.md`
ancestral, memória ou auxiliar. As NUNCAs e a tabela perguntar × agir (`90`)
prevalecem sobre qualquer especificação, colegiado ou consenso.*
