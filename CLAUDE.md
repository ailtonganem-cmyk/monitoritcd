# MonitorITCD



Roteamento de esforço: skill `adaptive-effort-router` (ver AGENTS.md).

<!-- project-lessons-library:begin v2 -->
## Biblioteca de aprendizados e insights do projeto

A skill `project-lessons-library` está disponível. No início da sessão, apenas
reconheça esta política; não carregue a skill nem leia `.agent-library/` por
inteiro. Ative-a ao investigar erros, falhas de build/test/runtime/deploy, antes
de repetir uma correção malsucedida, ao trabalhar em área com armadilhas,
invariantes ou decisões conhecidas, e depois de comprovar um aprendizado ou
insight não óbvio que possa tornar trabalhos futuros materialmente mais rápidos,
seguros ou corretos. Pesquise primeiro o índice local e leia somente os registros
mais relevantes. Registre apenas conhecimento comprovado, não trivial, acionável
e reutilizável; não registre observações rotineiras. O conhecimento local
prevalece sobre o compartilhado e todo registro deve ser revalidado contra o
código, as configurações e os requisitos atuais.
<!-- project-lessons-library:end -->

<!-- autonomo:begin v1 -->
## Modo autônomo (somente `/autonomo`)

A skill `autonomo` está instalada. **Não** carregue o corpo e **não** entre em
modo autônomo por conta própria, nem porque existe backlog, plano ou tarefa
aberta. Ative **somente** se o usuário invocar `/autonomo` (Codex `$autonomo`)
nesta sessão. Sem esse comando, ignore.
<!-- autonomo:end -->

<!-- novahabilidade:begin v1 -->
## Nova habilidade (pesquisa YouTube → skill)

A skill `novahabilidade` está disponível. No início da sessão, apenas reconheça
esta política; não carregue o corpo. Ative-a quando a tarefa exigir domínio que
você não tem completo, ou quando o usuário pedir para pesquisar um tema no
YouTube e transformar em skill reutilizável. Selecione os 20 principais vídeos
dos últimos 6 meses, exporte transcrições, consolide uma skill com mais peso
nos pontos que se repetem, instale em `~/Projetos/Skill` e propague com
`instalar.sh`. Não invente fatos de memória nem copie skill de terceiro.
<!-- novahabilidade:end -->

<!-- grafica:begin v2 -->
## Gráfica e qualidade visual

A skill `grafica` está disponível. No início da sessão, apenas reconheça esta
política; não carregue o corpo. Ative-a em tarefas de renderização, gráficos de
boa qualidade, imagens, mockups, conceitos visuais ou UI/design visual. Fluxo:
ensure Blender+MCP (porta 9876) **pelo agente, sem perguntar** → brief → conceito
→ iterações → gate de qualidade antes de entregar. Blender é o padrão; Figma é
apoio; MCPs pagos só sob pedido explícito.
<!-- grafica:end -->

<!-- vibecode:begin v1 -->
## Vibecode (sob demanda)

A skill `vibecode` está disponível. Na abertura, só reconheça; não carregue o
corpo. Ative em loops FE/BE/DB/UI ou com `/vibecode`. Checklists curtos
(orquestração, tokens, segurança, FE, BE/DB, tasks) sem reabrir PREVC, sem
subir R e sem inventar suíte. Alias: `/vibecoding`.
<!-- vibecode:end -->

<!-- mannered-prose:begin v1 -->
## Estilo: prosa direta (mannered-prose)

Prosa afetada (*mannered prose*) troca afirmação direta por metáfora e floreio.
Em vez de "um parâmetro que vale variar", escreve "a dial worth turning";
em vez de "este ponto ainda importa", escreve "this point earns its keep".
Essas frases exibem o escritor, não a ideia — e o leitor percebe. Irritam
porque fazem o leitor trabalhar mais para o escritor se exibir; também são
imprecisas: metáforas trazem conotações que você não escolheu nem controla.
A correção é dizer o que se quer dizer. Quando houver frase literal, use-a.
Aplique em chat, commits, PRs, planos e documentação gerada nesta sessão.
<!-- mannered-prose:end -->

Contrato = AGENTS.md deste diretório; PREVC e suíte estão lá. Skills: ver `Skill/CATALOGO-SKILLS.md` (corpo só no gatilho).
Siga `AGENTS.md` neste diretório.
`CLAUDE.md` é adaptador e não redefine precedência.

<!-- orca-worktree-cleanup-policy -->
## Worktrees Orca — limpeza após merge

Após a tarefa do worktree ser mergeada/incorporada à branch principal (`main`/`master` conforme o repo), a worktree Orca e a branch local correspondente **devem** ser removidas — não deixar lixo no projeto.

- Preferir: `orca-ide worktree rm --worktree … --force --json` (Linux: sempre `orca-ide`, nunca `orca` nu) ou exclusão pela UI do Orca.
- Não tentar apagar a worktree de dentro dela se isso falhar; pedir limpeza de fora / script / usuário.
- Isto é política para agentes; a limpeza automática confiável é o timer do sistema `orca-worktree-cleanup`.
<!-- /orca-worktree-cleanup-policy -->

<!-- EAW:BEGIN -->
@AGENTS.md
No início de tarefa, use o skill `eaw-router` e obedeça o bloco EAW de `AGENTS.md`.
Não redefina precedência aqui.
<!-- EAW:END -->

