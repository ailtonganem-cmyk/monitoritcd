# 80 — Git, entrega e documentação (Definition of Done)

> Fonte da verdade de **como o trabalho vira commit, entrega e registro**.

## Onde o trabalho roda — no branch principal [2026-08-16 v6]

**Tudo acontece no branch principal do repositório.** Sem worktree, sem branch
por tarefa, sem checkout paralelo — a determinação anterior de worktree está
**revogada**.

Na prática: o orquestrador commita direto no branch principal, sempre com
**pathspecs específicos** (nunca `git add .`); mudanças de outra frente que
estejam na árvore **não são tocadas**; e trabalho não commitado de terceiro
nunca é limpo, sobrescrito ou revertido.

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
