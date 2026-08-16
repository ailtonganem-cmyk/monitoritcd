# `regras/` — fonte da verdade das regras do MonitorITCD

Estrutura **hub-and-spoke**, portátil entre projetos e neutra a fornecedor
(Claude Code, Codex/ChatGPT, Gemini CLI, Grok, opencode, Cursor…). Adotada em
2026-08-13 por determinação do dono, a partir do template `Doc Mds`.

## Arquitetura

- **Fonte da verdade = os módulos deste diretório.** Os hubs são índices finos.
- **`CLAUDE.md`** (raiz) — hub lido pelo Claude Code; além do índice, só o que é
  específico do Claude (memória persistente, subagentes) e a cláusula de
  precedência sobre `CLAUDE.md` de diretórios ancestrais.
- **`AGENTS.md`** (raiz) — hub no padrão aberto AGENTS.md, lido por Codex,
  Gemini CLI, Copilot, Cursor, opencode e também pelo Claude Code. Contém o
  índice e o contrato mínimo do executor.
- Cada hub referencia o outro; **em divergência entre hubs, vale o módulo**.
- **Hubs curtos por design** (~120-160 linhas): instrução sempre-carregada acima
  de ~150 itens degrada a obediência do modelo. O detalhe fica no módulo,
  carregado sob demanda.

## Mapa dos módulos

| Módulo | Conteúdo | Específico do projeto? |
| --- | --- | --- |
| `00-identidade-projeto.md` | Identidade, pessoas, IDs, stack, execução autônoma | **Sim** |
| `10-metodo-trabalho.md` | PREVC, SPEC de Execução, verificação com evidência, ritmo, GSD | Não |
| `20-orquestracao-modelos.md` | Papéis, tabela nome↔papel, regras de despacho | Não (tabela atualizável) |
| `30-memoria-compartilhada.md` | Estado por tarefa em `_trabalho/`, protocolo entre agentes | Não |
| `40-regras-negocio.md` | Domínio ITCD/sucessões/regime de bens, fatos protegidos, LLM, UFs ativas | **Sim** |
| `50-saidas-notificacoes.md` | E-mail, Telegram, bot, severity tiers | **Sim** (substitui o `50-frontend` do template — projeto headless) |
| `60-backend.md` | Segurança server-side, `input_limits`, secrets, persistência, deploy | **Sim** |
| `70-testes-validacao.md` | Gates objetivos, prova por mutação, armadilhas conhecidas | **Sim** |
| `80-git-e-entrega.md` | Tudo na main, commits, DoD, documentação durável | Não |
| `90-seguranca-limites.md` | NUNCAs, tabela perguntar × agir, autorização durável | Não |

Conhecimento técnico durável (arquitetura C4, STRIDE, runbooks, ADRs, situação
das fontes por UF) **não** vive aqui — vive em `docs/`, referenciado pelos
módulos. Regra vinculante fica no módulo; descrição fica em `docs/`.

## Manutenção

- Regra recorrente (≥ 2 sessões), universal e de alto custo de violar →
  **promover** para o módulo correspondente (e, se crítica, resumir no hub).
- Modelo de IA novo lançado → atualizar **apenas a tabela** do módulo `20`, e só
  com nome verificado no fornecedor.
- Armadilha nova paga → uma linha no módulo `70`, no mesmo trabalho.
- Remover regra quando a convenção mudar — arquivo curto e vivo vale mais que
  arquivo completo e apodrecido.
