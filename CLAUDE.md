# MonitorITCD

Siga `AGENTS.md` neste diretório.
`CLAUDE.md` é adaptador e não redefine precedência.
Consulte `/home/ailtonganem/Projetos/Skill/ATIVACAO.md` para decidir qual skill abrir.

<!-- HML-LOCAL:begin v4 -->
## Homologação local + UI (permanente)

1. **HML = localhost.** Não criar/usar Firebase de HML. Local cobre **todas** as
   funções de produção (emuladores preferidos; senão recursos de **prod** com contas de teste).
2. Antes de `/produção`: bateria completa no HML local. Mudança de UI exige **Playwright**.
3. UI (criar/alterar/corrigir): **protótipo** para aprovação **antes** de fechar a tarefa.
4. Frontend/UI: **Antigravity (`agy`)**; outro agente só se agy impossível
   (`~/Projetos/Skill/compartilhado/llm-ranking.yaml`).
5. **UI/auth:** usuário(s) de teste **provisionados pelo sistema** (seed/bootstrap/emulador),
   **sem** cadastro manual. **Auto-login / sessão de teste só em localhost** (nunca em
   produção). Mínimo automação + admin; Google `ailtonganem@gmail.com` se Google Auth;
   senão credenciais de teste documentadas + seed no setup. Playwright e Design Mode
   usam essa sessão. Novo projeto: seed + auto-login HML antes de HML “pronto”.
6. Firebase **só-HML**: listar e excluir depois — **nunca** apagar produção.

### Orca ADE (obrigatório quando usar Orca)

7. Worktree com `scripts.setup` (inclui seed se UI/auth); `defaultTabs` `dev`
   (+ `emuladores` se Firebase); `.worktreeinclude` para `.env`; `sharedDirectories`
   **sem** `node_modules` se o lock diverge.
8. **Browser / Link Routing (obrigatório):** links `http(s)` abrem no **browser embutido**
   do worktree (`openLinksInApp = true`). Escape: `Shift+Ctrl+clique` → browser do sistema.
   **1Password:** extensão **não** instala no Chromium embutido — usar import cookies /
   perfis Orca / auto-login HML; 1Password no Chrome do sistema via escape hatch.
   Canônico: `~/Projetos/Skill/compartilhado/ORCA-BROWSER-LINKS.md`.
9. Esperar setup; subir dev (+ emuladores); abrir **localhost** já autenticado (sessão de teste)
   **só** no browser do worktree (Design Mode exige isso).
10. Portas **únicas** por projeto — mapa `ORCA-HML-PORTAS.md` quando existir.
11. Review de UI: **Design Mode** (feature correta) + Playwright na sessão de teste; FE = Antigravity.

Canônico: `~/Projetos/Skill/compartilhado/HML-LOCAL.md` (+ `ORCA-HML-LOCALHOST.md`,
`ORCA-BROWSER-LINKS.md`, `FLUXO-PRODUCAO.md`).
Yaml/`orca.yaml` nos repos: bot Orca ADE (não este catálogo).
<!-- HML-LOCAL:end -->

<!-- autonomo:begin v2 -->
## Modo autônomo (alias de `/loop`)

`/autonomo` e `/autonoma` são aliases da skill `loop`. **Não** always-on.
Ative **somente** com o comando expresso. Ver bloco `loop`.
<!-- autonomo:end -->

<!-- loop:begin v2 -->
## Loop de fila (somente `/loop`)

Skill `loop` (aliases `/autonomo`, `/autonoma`). **Só** com invocação expressa.
Drena **todas** as pendências (fila `tarefas`, plano, achados, PRs/issues, handoff).
Wakeup 60s **com disparo** entre tarefas: ao concluir um item, agendar retoma em 60s (`ScheduleWakeup` / `CronCreate` / nativo do CLI — ver `autonomo/references/cli-adapters.md`); **só então** executar o próximo. **Proibido** encadear itens sem esse disparo. Fallback in-session (aguardar no turno ~60s) **somente** se o CLI **não tiver** scheduler documentado.
Para só com fila vazia/sem jobs ou cancel do usuário. Não always-on.
`/loop` **não** autoriza `/produção`. No Claude Code, `/loop` nativo é scheduler —
o contrato de fila é esta skill (use o nativo **como** o disparo de 60s).
<!-- loop:end -->

<!-- automelhoramento:begin v2 -->
## Automelhoramento (somente `/automelhoramento`)

Skill `automelhoramento`. **Só** com invocação expressa. Ciclo: auditoria completa
→ itens em `tarefas` → `/loop` → após cada etapa `/produção` (**este slash autoriza**
produção no ciclo, fail-closed) → nova auditoria. Para só com cancel expresso.
Wakeup 60s **com disparo** entre tarefas: ao concluir um item, agendar retoma em 60s (`ScheduleWakeup` / `CronCreate` / nativo do CLI — ver `autonomo/references/cli-adapters.md`); **só então** executar o próximo. **Proibido** encadear itens sem esse disparo. Fallback in-session (aguardar no turno ~60s) **somente** se o CLI **não tiver** scheduler documentado.
Vale **também** entre etapas do ciclo e entre reauditorias.
UI/FE = Antigravity; HML = localhost; sem perguntas no miolo.
<!-- automelhoramento:end -->

<!-- producao:begin v2 -->
## Produção (`/produção`)

Skill `producao`. **Só** com `/produção`, `/producao` ou `$producao` — o slash é
autorização founder — **ou** dentro do ciclo ativo de `/automelhoramento` (exceção
documentada; fail-closed). `/loop` / `/autonomo` **não** autorizam produção.
Não always-on; fecha merges/PRs prontos, limpa worktrees mergeadas, entrypoint
canônico do AGENTS (fail-closed se CI/check vermelho). Não reabre PREVC.
<!-- JEV-SESSAO -->
## Jev — always-on de decisão

Desde o início de **toda** sessão: em cada **fork material** (decisão), consultar Jev
(Choice/Score/Noul) **antes** de comprometer o ramo. Não é ATIVADO de skill KEEP.

- Contrato: `~/Projetos/Skill/compartilhado/JEV-SESSAO.md` (B1/B2, §4b, Outpost/Adapter, idioma EN, degradação)
- Helper: `~/Projetos/Skill/tools/jev-eval/jev-eval.sh` (`--backend auto|jev|adapter`)
- **Perguntas ao Jev/Adapter em inglês**; prosa ao Ailton em pt-BR
- **Confiança ≤70%:** contestar + reperguntar (EN); se ainda ≤70% → **Ailton** (sessão normal) ou **3 agentes** (`/autonomo`)
- `/autonomo`|`/loop`: Jev decide quando disponível e confiança >70%; reabrir só com evidência nova; teto N=3;
  ao **drenar a fila sem impeditivo**, disparar **`/produção` automaticamente**
- **Cascata Outpost:** Jev nativo → se falhar e sessão **fraca** → System One Adapter + modelo **fronteira** (mesmas perguntas; tag `backend=adapter`) → senão PREVC **sem** árbitro. Jev OK = **não** trocar por Adapter. Proibido Adapter com o mesmo modelo fraco da sessão.
- Jev/Adapter **não** escrevem código e **não** autorizam `/produção`/merge sozinho

**Pacotes 2026-09-19:** ver `JEV-SESSAO.md` §§10–13 e `~/Projetos/Skill/compartilhado/jev-implementacao-20260919/` (Grok Bot/CU, Spark/Cowork doc, shadow gates, hooks CLI). Shadow only até calibração.
**Onda 2 (2026-09-19):** núcleo `~/Projetos/Skill/compartilhado/jev-implementacao-20260919/onda2/` — antes de despachar especialista: `wrappers/cli-session-router.sh`; browser embutido CU A–E: `wrappers/cu-stagehand-act.sh`; citation/RAG/semantic onde houver base. Fail-open se Jev down. Sem Ollama Act. Nunca `/produção` via Jev.
**Onda 3 (2026-09-19):** Router Layer — antes de despachar especialista/worktree: `~/Projetos/Skill/compartilhado/jev-implementacao-20260919/onda3/wrappers/task-envelope.sh` + `skill-router.sh`; respeitar `apply.specialist` (mapa bots). UI→`antigravity_ui`. Fail-open. Nunca `/produção` via Jev. Doc: `onda3/BRIEF.md` + `PROPOSTA-JEV-TOOL-ROUTER-20260919.md`.
<!-- /JEV-SESSAO -->
<!-- producao:end -->
