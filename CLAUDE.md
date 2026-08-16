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

## §0 — Método PREVC, três papéis [v6]

**Método único: PREVC.** **Orquestrador** (pensamento, planejamento, gerência) →
**Executor** (codificação) → **Revisor** (verifica e valida se o planejado foi
feito e está correto). O orquestrador apresenta o **plano de trabalho completo**
— objetivo, escopo, arquivos, spec, critério de aceite, como validar — e
classifica o **nível: simples · média · complexa**; com base nele escolhe
**executor, revisor e esforço** (`regras/20`), despacha, integra e reporta. O
**Gauntlet** só por escolha expressa do orquestrador.

**Piso:** gates verdes com saída literal · revisor ≠ executor · NUNCAs e
perguntar×agir · fatos protegidos. Anti-loop: 3 idas e voltas → escalar.
**Tudo roda no branch principal — sem worktree.**

## Ritmo

Autonomia **dentro** da tarefa; concluída, reportar e prosseguir à próxima.

## Papéis e agentes (resumo)

**Orquestrador** planeja e gerencia · **Executor** codifica (simples → Grok ·
opencode DeepSeek v4 Pro · Sonnet 5 · Luna; média → Grok · Sonnet 5 · Terra ·
opencode; complexa → Grok · Opus 5 · Terra) · **Revisor** valida (Opus 5 ou
Terra ou superior, nunca quem executou). Escolha e esforço são do orquestrador.
Ao fim de cada etapa **há comunicação entre os agentes, documentada**.
Detalhe: `regras/20-orquestracao-modelos.md`.

## Onde o trabalho roda

**Tudo no branch principal** — sem worktree, sem branch por tarefa
(`regras/80-git-e-entrega.md`).

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
| Método PREVC, três papéis, níveis e plano | `regras/10-metodo-trabalho.md` |
| Papéis e agentes (orquestrador · executor · revisor) | `regras/20-orquestracao-modelos.md` |
| Regras de negócio: domínio, fatos protegidos, LLM, UFs | `regras/40-regras-negocio.md` |
| Saídas: e-mail, Telegram, bot | `regras/50-saidas-notificacoes.md` |
| Backend: segurança, limites, secrets, persistência | `regras/60-backend.md` |
| Testes, gates e armadilhas conhecidas | `regras/70-testes-validacao.md` |
| Git (tudo na main) e entrega | `regras/80-git-e-entrega.md` |
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
