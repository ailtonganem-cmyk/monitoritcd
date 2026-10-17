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

## Pendência frota regra de negócio e Excalidraw (2026-10-17)

### RN-BACKEND-001 — Verificar regras de negócio no front-end e migrar para o back-end

- **Risco:** R2 · **C:** C2
- **Estado:** pronto
- **Pedido:** Verificar se há regras de negócio no front-end e, se houver, migrá-las para o back-end. Decisão do Ailton (2026-10-17): o servidor decide e faz valer a regra; o front-end só exibe e valida a UX.
- **Aceite:** inventário das regras encontradas no front-end (arquivo:linha); cada uma migrada para o back-end com teste no servidor, ficando no cliente só a validação de UX; `## Perfil de testes` do AGENTS.md com `- Regras de negócio: back-end (<caminho>)` ou `n/a (motivo)`; `homologar.sh rodar` sem aviso nem rejeição de regra de negócio. Mudança de comportamento da regra = PENDENTE com o Ailton (nunca default).
- **Refs:** bloco METODO (Regra de negócio no back-end) · `~/Projetos/Skill/compartilhado/TESTES.md` §7.2
- **Registrado:** 2026-10-17 (FazTudo/Grok Skill, sem executar agora)

### EXCALIDRAW-001 — Estudo do Excalidraw neste projeto

- **Risco:** R1 · **C:** C1
- **Estado:** pronto
- **Pedido:** Estudar o uso do Excalidraw neste projeto a partir de `~/Projetos/Estudos/excalidraw/estudo.md` (versão mais recente na hora, sem fixar). Diagramas da SPEC já seguem o formato `docs/diagramas/<id>.excalidraw.svg` (skill `spec` §5a).
- **Sugestões do estudo que se aplicam:** A1 diagramas da SPEC/fase P-R em `.excalidraw.svg` via MCP local `mcp-excalidraw-server`; A2 extensão VS Code `pomdtr.excalidraw-editor` para revisar nos PRs.
- **Ideias novas:** (1) diagrama do pipeline de monitoramento (fontes → coleta → alertas); (2) máquina de estados do processo ITCD monitorado; (3) runbook visual de incidente.
- **Aceite:** nota em `docs/estudos/` com decisão por ideia (fazer/adiar/não), esforço e riscos (bundle, acessibilidade, dado sensível em MCP remoto); nada implementado sem ordem.
- **Registrado:** 2026-10-17 (FazTudo/Grok Skill, sem executar agora)

## Pendência frota teste de regressão (2026-10-17)

### REGRESSAO-001 — Teste de regressão em toda correção de bug

- **Risco:** R2 · **C:** C2
- **Estado:** pronto
- **Pedido:** Adotar a regra do método (Ailton 2026-10-17): todo commit `fix:` traz teste novo ou alterado que falha no código anterior e passa depois, com o trailer `Regressao-teste: <caminho>::<nome>`. Isenção só com `Regressao-isento: <motivo>` da lista fechada (doc, config, infra, deps, build, nao-reproduzivel; este exige tarefa no TAREFAS.md). Commit sem `fix:` com corrige/bug/fix só gera aviso.
- **Aceite:** marcador `regressao` na camada mais baixa que reproduz o bug, com id da issue/tarefa/SHA (`@pytest.mark.regressao` + `test_regressao_<id>` ou `describe('regressao: <id>')`; pasta `tests/regressao/` só sem marcador); linha `[regressao]` em `## Comandos` com `{teste}` se o runner não for pytest; hook `commit-msg` ativo (`~/Projetos/Skill/instalar.sh`, ou encadeado no husky/.githooks/hook próprio do projeto); job `regressao` do `checks.yml` do template se houver CI; `- Regressão: <marcador/local>` preenchida em `## Perfil de testes`. Preencher essa linha fecha esta tarefa e liga o bloqueio (até lá, hook/homologar/CI só avisam).
- **Refs:** `~/Projetos/Skill/compartilhado/TESTES.md` §7.3 (D9) · bloco METODO (Regressão)
- **Registrado:** 2026-10-17 (FazTudo/Grok Skill, sem executar agora)
