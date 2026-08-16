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
no branch principal — ver Git, abaixo).

## Idioma

**Somente português brasileiro** em tudo: comentários, docstrings, testes,
commits, relatórios, mensagens ao dono, conversa. Ortografia rigorosa.
**Identificadores de código permanecem em inglês**, exceto termos jurídicos sem
tradução fiel (`causa_mortis`, `espolio`, `inventario`, `doacao`).



## Git — escrita exclusiva do coordenador

**Tudo roda no branch principal** — sem worktree, sem branch por tarefa.
Executores **não usam git para escrever** (`add`, `commit`, `stash`,
`checkout`, `restore`, `reset`, `clean`); leitura é livre. Mudança em
arquivo que você não tocou é de outra frente: não reverta, não "conserte".
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
| Método PREVC, três papéis, níveis e plano | `regras/10-metodo-trabalho.md` |
| Papéis e agentes (orquestrador · executor · revisor) | `regras/20-orquestracao-modelos.md` |
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
