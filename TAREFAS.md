# TAREFAS

Fila canônica do projeto (skill `tarefas`).

## Reforma do método (2026-09-23)

### MET-T3-PISO — Completar o piso T3 da seção Comandos
- **Tier:** T3 · **C:** C2 · **Estado:** implementado (2026-09-23); falta confirmar o `tests.yml` verde no CI depois do push · **Origem:** reforma do método 2026-09-23 (decisão de Ailton)
- **Pedido:** falta `[build]` (não há build local) no piso `[build] [testes] [segredos] [dependencias]`; sem isso o projeto não publica
  por sinal verde (`verificar-veredito.sh` sai com 4).
- **Sugestão (conferir antes de adotar):** empacotamento `python -m build` ou equivalente já usado no deploy das Functions.
- **Aceite:** comando real no repositório, etiquetado na seção `## Comandos` do `AGENTS.md`, rodando verde no CI e
  no `homologar.sh rodar`; a linha "Lacuna declarada (piso T3)" sai de `## Limites`.
- **Fora de escopo:** corrigir achados que o novo gate apontar (viram itens próprios).

## Revisão do método — Rodada 4 (2026-10-24)

### REV24-P5 — gitleaks.toml sem literais de canário e sem regex global de chave privada; baseline sem allowlist

- **Tier:** T2 · **Nível:** S1 · **Estado:** pronto
- **Origem:** Revisão total do método, Rodada 4 (ADENDO-1510), conferência de implementação (2026-10-24); situação conferida: .gitleaks.toml tem literais de canário AWS e regex global 'PRIVATE KEY'; .secrets.baseline marca 19 hex como não segredo (PR #75).
- **Plano:** `docs/planos/REV24-P5.md`
- **Aceite:** Dado a main, quando `gitleaks dir .` e `detect-secrets scan` rodam, então não há achado nem allowlist.

### REV24-P10 — Runner self-hosted para o security.yml

- **Tier:** T2 · **Nível:** S0 · **Estado:** pronto
- **Origem:** Revisão total do método, Rodada 4 (ADENDO-1510), conferência de implementação (2026-10-24); situação conferida: repo sem runner; Secret scanning falha (run 39212947984).
- **Plano:** `docs/planos/REV24-P10.md`
- **Aceite:** Dado a main, quando o security.yml roda, então sai success em runner book-*.
