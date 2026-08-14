# 80 — Git, entrega e documentação (Definition of Done)

> Fonte da verdade de **como o trabalho vira commit, entrega e registro**.

## Worktree por tarefa — obrigatória, sem exceção [determinação do dono 2026-08-13]

**Toda tarefa — independente do porte, inclusive trivial — é realizada em
worktree git própria.** A árvore principal (`C:\Projetos\MonitorITCD`) nunca
recebe edição direta de tarefa.

Fluxo canônico, todo ele executado pelo **orquestrador**:

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
6. Worktree é **descartável**: tarefa abortada → remover sem merge; nunca
   reaproveitar worktree de uma tarefa em outra.

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
