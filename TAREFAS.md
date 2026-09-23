# TAREFAS

Fila canônica do projeto (skill `tarefas`).

## Reforma do método (2026-09-23)

### MET-T3-PISO — Completar o piso T3 da seção Comandos
- **Tier:** T3 · **C:** C2 · **Estado:** pronto · **Origem:** reforma do método 2026-09-23 (decisão de Ailton)
- **Pedido:** falta `[build]` (não há build local) no piso `[build] [testes] [segredos] [dependencias]`; sem isso o projeto não publica
  por sinal verde (`verificar-veredito.sh` sai com 4).
- **Sugestão (conferir antes de adotar):** empacotamento `python -m build` ou equivalente já usado no deploy das Functions.
- **Aceite:** comando real no repositório, etiquetado na seção `## Comandos` do `AGENTS.md`, rodando verde no CI e
  no `homologar.sh rodar`; a linha "Lacuna declarada (piso T3)" sai de `## Limites`.
- **Fora de escopo:** corrigir achados que o novo gate apontar (viram itens próprios).
