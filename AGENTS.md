# MonitorITCD — AGENTS.md (hub)

> Hub no padrão aberto AGENTS.md, para **qualquer agente de IA** que trabalhe
> neste repositório — Codex/ChatGPT, Gemini CLI, Grok, opencode, Cursor, Copilot
> e também o Claude Code. **A fonte da verdade são os módulos em `regras/`** —
> este arquivo é o índice e o contrato mínimo do executor. O `CLAUDE.md` é o hub
> gêmeo com as particularidades do Claude Code; em divergência entre hubs,
> **vale o módulo**.

## O projeto em uma tela

**MonitorITCD** — sistema headless, single-user, que monitora mudanças
legislativas, normativas e jurisprudenciais sobre **ITCD/ITCMD/ITD**,
**Sucessões** e **Regime de Bens**, classifica por LLM e notifica o dono por
e-mail e Telegram. Python ≥ 3.11 · Firebase · GitHub Actions. Escopo ativo:
**MG + fontes federais**.

Identidade, pessoas, IDs, stack e a regra de execução autônoma:
`regras/00-identidade-projeto.md` — **leia antes de qualquer tarefa**.
Working directory canônico: `C:\Projetos\MonitorITCD` (mas o trabalho acontece
na worktree da tarefa — ver Git, abaixo).

## Idioma

**Somente português brasileiro** em tudo: comentários, docstrings, testes,
commits, relatórios, mensagens ao dono, conversa. Ortografia rigorosa.
**Identificadores de código permanecem em inglês**, exceto termos jurídicos sem
tradução fiel (`causa_mortis`, `espolio`, `inventario`, `doacao`).

## Método — PREVC e SPEC de Execução

Toda tarefa segue **P**lanejamento → **R**evisão → **E**xecução → **V**alidação →
**C**onfirmação (`regras/10-metodo-trabalho.md`). **A formalidade escala com a
trilha** [v3]: **Direta** (padrão — um único agente conduz P+E+V, validação por
gates objetivos, sem SPEC em arquivo nem crítico separado) · **Padrão**
(SPEC-lite de 5 campos + crítico separado na entrega) · **Gauntlet** (pipeline
completo, alto risco e acabamento). Quem encontrar risco não previsto **sobe a
tarefa de trilha** e registra o motivo.

- **Se você orquestra (Codex — GPT-5.6 Sol, esforço máximo — techlead):**
  gerencie e distribua — pense sempre nos limites de uso de cada agente,
  despache o planejador, dispare executores e críticos conforme a SPEC, integre
  e reporte. **Não escreva SPEC, não crie nem revise código** (`regras/20`).
- **Se você planeja (planejador — por despacho do orquestrador):** produza a
  **SPEC de Execução escrita** com a **complexidade classificada** antes de
  qualquer edição — em `specs/SPEC_<ID>_<slug>.md` para tarefa média/grande — e
  devolva ao orquestrador, que despacha os executores.
- **Se você codifica (executor):** **sem SPEC, não comece** — despacho sem SPEC
  ou com seção material vazia é devolvido ao orquestrador. Implemente com
  fidelidade; ambiguidade → interpretação razoável + suposição registrada no
  relatório. **Nunca invente fato normativo** (`regras/40-regras-negocio.md`).

Papéis e modelos: `regras/20-orquestracao-modelos.md`.

## Memória de trabalho compartilhada

Cada tarefa tem estado em `_trabalho/ESTADO_<id>.md`, que **todo agente lê ao
iniciar e atualiza ao concluir etapa** — decisões, arquivos em edição, progresso,
achados. **Declare o arquivo antes de editá-lo.** Protocolo:
`regras/30-memoria-compartilhada.md`.

## Git — worktree por tarefa; escrita exclusiva do coordenador

**Toda tarefa roda em worktree git própria** (`../MonitorITCD-worktrees/<id>`),
criada pelo orquestrador — nunca edite a árvore principal. A worktree tem
`.venv` próprio (nunca symlinkado). Executores **não usam git para escrever**
(`add`, `commit`, `stash`, `checkout`, `restore`, `reset`, `clean`); leitura
(`diff`, `log`, `status`, `show`) é permitida. Mudança em arquivo que você não
tocou é de outro agente — não reverta, não "conserte".
Detalhe: `regras/80-git-e-entrega.md`.

## Regras invioláveis (resumo)

- **NUNCA inventar** fato, número, lei, alíquota, prazo ou jurisprudência —
  aponte a fonte a consultar, não preencha. Vale também para o texto que o LLM
  do pipeline gera (`regras/40-regras-negocio.md`).
- **NUNCA alterar conteúdo coletado** — `original` é write-once; resumo preserva
  nomes, números e datas verbatim.
- **NUNCA hardcodar secrets**; **NUNCA confiar na entrada** (inclusive a do dono
  pelo bot).
- **NUNCA `git add .`**; **NUNCA `--no-verify`** sem motivo documentado.
- **NUNCA apagar dados de produção em massa**; **NUNCA** aceitar termos ou
  autorizar pagamento.
- **NUNCA concluir com gate vermelho** (`regras/70-testes-validacao.md`).
- **Não mexa em código não relacionado** — problema fora do escopo é relatado
  como questão separada.
- Lista completa e tabela perguntar × agir: `regras/90-seguranca-limites.md`.

## Ritmo

Autonomia total **dentro** da tarefa; concluída a tarefa, **reportar com
evidência e aguardar** determinação do dono. Não encadeie tarefas por conta
própria.

## MCPs e superfícies

**Havendo possibilidade técnica, resolva a tarefa via MCP** — o **planejador**
indica na SPEC qual utilizar (candidatos aqui: Firebase, Chrome DevTools); o
**orquestrador** confere vinculação e limites antes do despacho. MCP indicado
porém **não vinculado** ao seu agente → devolva o
bloqueio ao orquestrador, que conduz a vinculação com o dono guiando o login
(credenciais nunca passam pelo agente). Detalhe: `regras/10-metodo-trabalho.md`, princípio 7.

## Verificação — "como você me confirma que isso está correto?"

Antes de executar, descreva como vai executar; depois, **verifique ativamente e
relate a evidência** (saída literal dos gates), não a conclusão. Gates,
limiares e armadilhas conhecidas: `regras/70-testes-validacao.md`.

## Índice — fonte da verdade

| Assunto | Módulo |
| --- | --- |
| Identidade do projeto | `regras/00-identidade-projeto.md` |
| Método de trabalho (PREVC, SPEC, GSD) | `regras/10-metodo-trabalho.md` |
| Orquestração e modelos | `regras/20-orquestracao-modelos.md` |
| Memória compartilhada | `regras/30-memoria-compartilhada.md` |
| Regras de negócio (domínio, LLM, UFs) | `regras/40-regras-negocio.md` |
| Saídas: e-mail, Telegram, bot | `regras/50-saidas-notificacoes.md` |
| Backend: segurança, limites, secrets | `regras/60-backend.md` |
| Testes e validação | `regras/70-testes-validacao.md` |
| Git, entrega e documentação | `regras/80-git-e-entrega.md` |
| Segurança e limites | `regras/90-seguranca-limites.md` |

## Quando parar e perguntar ao dono

Dinheiro, remoção de funcionalidade, ação destrutiva em dados, ativação de UF,
mudança de severity tier ou de provedor de LLM, dado real de terceiros, ou
informação que só ele tem. Fora disso: decida com razoabilidade, **anuncie a
escolha e o motivo**, e siga.
