# 80 — Git, entrega e documentação (Definition of Done)

> Fonte da verdade de **como o trabalho vira commit, entrega e registro**.

## Worktree — por risco, com pool pré-aquecido [dono 2026-08-14 v3 — substitui a obrigatoriedade sem exceção de 2026-08-13]

> **Por que mudou:** worktree nova a cada tarefa exige recriar o `.venv` antes
> do primeiro commit — minutos de espera para mudar uma mensagem. O isolamento
> fica onde protege; o pedágio sai de onde não protegia nada.

**A worktree é a FRENTE de trabalho, não a tarefa** [founder 2026-08-16]: tarefa
que **continua, corrige ou complementa** trabalho de uma worktree ativa, ou que é
da **mesma frente** (mesmos arquivos/módulo/feature), **roda dentro dela**;
tarefas pequenas e independentes do dia vão para a **worktree do dia**
(`dia-AAAA-MM-DD`) ou para o **pool**. Roteamento e ciclo de vida completos:
`25-harness-orca.md`. **Teto: 6 worktrees de tarefa por repositório** (fora os
checkouts principais e o pool) — atingido, reconciliar antes de abrir outra.

**Worktree NOVA só por motivo técnico declarado:** há **paralelismo real** (2+
agentes editando ao mesmo tempo); **refactor amplo** ou mudança multi-arquivo com
risco de regressão; **base branch diferente** da frente em curso; **experimento
descartável**; ou **o plano de trabalho pediu** (`10`).

**Encerrar o worker não remove a worktree:** fechar o terminal / liberar o
dispatch arquiva a execução, mas o checkout persiste até `orca worktree rm`.
Remover só com as **quatro confirmações** (sem terminal vivo · árvore limpa ·
commit integrado · nenhuma evidência exclusiva); parcial, bloqueada ou com patch
não integrado **mantém-se com comentário de estado** (`25`).

**Dispensada quando:** tarefa **sequencial, de um único agente e baixo risco**
— trabalha-se em **branch curto** na árvore principal, com
commit atômico e merge imediato. A árvore principal nunca fica com trabalho
pendente entre tarefas.

**Pool pré-aquecido:** as worktrees de `../MonitorITCD-worktrees/` são
**reutilizáveis** — mantenha 2–3 permanentes (`w1`, `w2`, `w3`) com `.venv`
próprio já criado. Para usar: `git checkout -B tarefa/<id>` a partir do `main`
atualizado; reinstalar dependências **só quando o `requirements` mudou**; ao
concluir, devolver ao `main` e **não remover** a worktree. **Nunca symlinkar
`.venv`** entre worktrees.

Fluxo canônico **quando a worktree é criada do zero**, executado pelo
**orquestrador**:

1. **Criar**, a partir do `main` atualizado:
   ```bash
   git worktree add ../MonitorITCD-worktrees/<id> -b tarefa/<id>
   ```
   A pasta de worktrees fica **fora** do repositório.
2. **Preparar** — worktree não herda `.venv` nem arquivos gitignored:
   ```bash
   python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"   # Windows
   python3 -m venv .venv && .venv/bin/python  -m pip install -e ".[dev]"     # WSL/Linux
   ```
   Copiar os arquivos listados em `.worktreeinclude` (`.env`,
   `.claude/settings.local.json`). **Nunca symlinkar `.venv`** entre worktrees —
   um `pip install` contamina todas (`70`).
3. **Trabalhar:** todos os agentes da tarefa, de qualquer fornecedor, operam
   **dentro da worktree**; o ESTADO compartilhado (`30`) vive em `_trabalho/`.
4. **Validar:** os gates (`70`) rodam **dentro da worktree** — nunca na árvore
   principal.
5. **Integrar:** com V verde, o orquestrador commita em `tarefa/<id>`, volta ao
   `main`, faz o merge, remove a worktree (`git worktree remove`) e o branch
   (`git branch -d` — nunca `-D`).
6. **Encerrar ≠ remover** [founder 2026-08-16]: integrada e validada, árvore
   limpa e sem valor de diagnóstico → descartar o checkout; **parcial, bloqueada
   ou com patch não integrado → manter, com nome e comentário de estado**.
   Tarefas da **mesma frente** reaproveitam a worktree em vez de abrir outra
   (`25`).

Subagentes com isolamento nativo por worktree (`isolation: "worktree"` no Claude
Code) podem usá-lo para frentes paralelas **dentro** da tarefa; a worktree da
tarefa continua sendo a unidade de integração.

> **Estado atual do working tree principal:** há ~275 arquivos marcados como
> modificados que são apenas conversão CRLF↔LF
> (`git diff --ignore-cr-at-eol --stat` volta vazio). Não misturar esse ruído em
> commit de tarefa — mais um motivo para a regra de worktree.

## Git — exclusivo do coordenador

- **Agentes executores não usam git para escrever.** Nada de `add`, `commit`,
  `stash`, `checkout`, `restore`, `reset`, `clean` — a worktree é compartilhada
  entre executores paralelos e um `stash/pop` já reverteu o trabalho alheio.
  Leitura (`diff`, `log`, `show`, `status`) é permitida.
- Modificação em arquivo que você não tocou é de outro agente: não reverta, não
  "conserte"; registre uma linha no ESTADO (`30`) se for relevante.
- **NUNCA `git add .`** — sempre pathspecs específicos (o repo tem ruído de EOL
  e artefatos locais).
- **NUNCA `--no-verify`** sem motivo documentado; hook falhou → investigar a
  causa, não contornar. Pre-commit é a barreira de secret (`60`).
- **NUNCA `push --force`** sem ordem expressa do dono (`90`).
- Push, deploy e disparo de workflow: livres **dentro da tarefa em curso**, com
  gates verdes (regra de execução autônoma — `00`).

## Commits

- Mensagem em pt-BR, tipo convencional (`feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`), descrevendo o **porquê** quando não-óbvio.
- Um commit por unidade lógica de entrega; o commit é o registro de atividade —
  não duplicar em log por-tarefa.
- Mensagem multi-linha: **a sintaxe depende do shell usado**. Here-string
  `@' … '@` é do PowerShell e **quebra no Bash** (o `@` entra na mensagem); no
  Bash, usar heredoc (`git commit -F - <<'EOF'`) ou `-F <arquivo>`. Conferir com
  `git log -1 --format=%B` antes de dar a tarefa por concluída.

## Definition of Done — persistir SÓ o durável

Documentação obrigatória apenas quando a mudança gera conhecimento **não
derivável do git log/código**:

| Tipo de mudança | Doc durável |
| --- | --- |
| Tarefa média/grande | SPEC em `specs/SPEC_<ID>_<slug>.md`, versionada (`10`) |
| Decisão arquitetural | `docs/adr/NNNN-<slug>.md` |
| Novo runbook operacional | `docs/runbooks/<slug>.md` |
| Fonte/UF nova ou alterada | `docs/ufs/{UF}.md` + `docs/UFS_STATUS.md` / `docs/sources_status.md` |
| Mudança de contrato visível ao dono (comando, digest, campo) | `README.md` + o módulo `regras/` correspondente |
| Bugfix/refactor sem doc própria | **nada** — o commit é o registro |

Regra recorrente (≥ 2 sessões), universal e cara de violar → **promover** para o
módulo `regras/` correspondente (e, se crítica, resumir no hub).

## Conclusão de tarefa

Concluir = **reportar ao dono com evidência verificável**: saída dos gates,
SHA do commit, o que foi conferido empiricamente e o que ficou pendente.
Critério de aceite: matriz de validação (`70`) + documentação durável vinculadas
ao mesmo SHA. Depois de reportar, **prosseguir imediatamente à próxima tarefa
da fila — Gauntlet Loop** (`10`).
