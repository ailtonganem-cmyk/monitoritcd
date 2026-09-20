# Inventário de IA do MonitorITCD e encaixe do Jev

Data: 2026-09-20. Sessão Orca, worktree `jev-ia-inventario-20260920`, branch
`ailtonganem-cmyk/jev-ia-inventario-20260920`, base `5440914`.
Escopo: somente este projeto. Sem merge, sem `/produção`, sem deploy nesta leva.

Este documento cataloga todo uso de modelo de IA no repositório e propõe onde o Jev
(TypeSafe, Choice/Score/Noul) entra como árbitro tipado. Nenhum segredo aparece aqui:
só nomes de variáveis de ambiente e caminhos de arquivo.

## 1. Resumo

O MonitorITCD usa IA em **uma única função de produto**: classificar itens coletados
(Filtro 2 da pipeline). Tudo o mais — provedores, cadeia de fallback, painel, workflows —
é infraestrutura em volta dessa função.

- **Modalidade:** exclusivamente **texto**. Zero áudio, imagem, vídeo, OCR, STT/TTS,
  vision, multimodal ou embeddings. Busca semântica e cosine estão marcados como TODO
  explícito em `src/monitoritcd/search.py:23-25`, sem implementação.
- **Provedores com adaptador:** Google Gemini, Groq, OpenAI, Anthropic, xAI, OpenRouter,
  DeepSeek, Ollama (loopback). Padrão em produção: Gemini → Groq.
- **Jev hoje:** **zero call sites**. A busca por `jev|typesafe|choice/score|noul` no
  repositório não retorna nenhuma ocorrência de código, hook, template ou documento.
  Todo encaixe abaixo é lacuna.
- **O que já existe e não deve ser reinventado:** validação pydantic estrita
  (`extra="forbid"`), versionamento de prompt com snapshot de regressão, pré-filtros
  determinísticos que barram a maior parte do volume antes do LLM, e regra de prompt
  que trata o conteúdo coletado como dado não confiável. O Jev entra **em cima** disso,
  não no lugar disso.

### Método e evidência da busca

```
grep -rEln "genai|openai|anthropic|groq|gemini|xai|deepseek|openrouter|ollama|llm|LLM|
  embedding|whisper|transcri|ocr|OCR|tesseract|vision" --include=*.py --include=*.ts
  --include=*.tsx --include=*.js --include=*.json --include=*.yaml --include=*.yml
  --include=*.toml --include=*.html .        # 92 arquivos, node_modules e .venv fora
grep -rniE "\bjev\b|typesafe|choice/score|noul" .   # nenhuma ocorrência
```

## 2. Inventário por call site

| # | Feature | Modalidade | Provedor | Call site | Jev hoje | Gate proposto | Prioridade |
|---|---|---|---|---|---|---|---|
| 1 | Classificação de itens (Filtro 2): relevância, tipo, tópicos, resumo, pontos-chave, tags | texto | cadeia configurável | `src/monitoritcd/filters/llm_classifier.py:342` `classify_with_provider` | não | `citation` — `classificacao_fundamentada` (noul) | **P0** |
| 2 | Campo `contexto`: único campo onde o prompt permite conhecimento jurídico geral | texto | idem | `src/monitoritcd/filters/llm_classifier.py:162,177` (prompt), `:318` (persistência) | não | `citation` — `risco_alucinacao_contexto` (score) | **P0** |
| 3 | System prompt dinâmico: descrições de tópicos criados via `/topicos` entram no prompt | texto | idem | `src/monitoritcd/filters/llm_classifier.py:117` `build_system_prompt`; origem em `src/monitoritcd/bot/handlers.py:469` | não | `guardrails` — `entrada_segura` (noul) | **P0** |
| 4 | Escalonamento CRITICO: push imediato no Telegram a partir da relevância do LLM | texto | idem | `src/monitoritcd/notifiers/severity.py:80` `effective_severity`; `src/monitoritcd/orchestrator.py:332` | não | `critico` — template de frota `monitor-itcd-critico.yaml` já existe | **P0** |
| 5 | Provedor Gemini (primário) | texto | Google, SDK `google-genai` | `src/monitoritcd/llm/gemini.py` | não | coberto por #1/#7 | P1 |
| 6 | Provedor Groq (fallback) | texto | Groq, HTTP OpenAI-compatible | `src/monitoritcd/llm/groq.py` | não | coberto por #1/#7 | P1 |
| 7 | Cadeia e fallback por quota (429/5xx → próximo; esgotou → defere o lote) | — | — | `src/monitoritcd/llm/fallback.py`, `src/monitoritcd/llm/cadeia.py:99` `montar_cadeia` | não | `material` — `rota_provedor` (choice, advisory) | P1 |
| 8 | Provedores OpenAI, xAI, OpenRouter, DeepSeek, Ollama | texto | HTTP chat/completions | `src/monitoritcd/llm/openai_compat.py:23` `OpenAICompatProvider` | não | coberto por #7; Ollama já restrito a loopback em `:41-45` | P1 |
| 9 | Provedor Anthropic (Messages API) | texto | Anthropic | `src/monitoritcd/llm/openai_compat.py:85` `AnthropicProvider` | não | coberto por #7 | P1 |
| 10 | Provedor fake (dry-run e CI, sem rede) | texto | nenhum | `src/monitoritcd/llm/fake.py` | não | **sem gate** — sem chamada externa | — |
| 11 | Pipeline: classificar em lotes de 10 e persistir | — | — | `src/monitoritcd/orchestrator.py:250` `classify_and_store` | não | ponto de chamada dos gates #1, #2, #4 | **P0** |
| 12 | Reprocessamento: sobrescreve `llm.*` de documentos já classificados | — | — | `src/monitoritcd/orchestrator.py:386` `reprocess_documents` | não | `destructive` — `reprocessamento_em_massa` (choice) | P1 |
| 13 | Comando `/reprocessar` do bot (confirmação em 2 passos, custo em LLM) | — | — | `src/monitoritcd/bot/handlers_extra.py:396` | não | mesmo gate de #12, antes de emitir o token | P1 |
| 14 | Painel: leitura e gravação da cadeia de IA (`GET`/`POST /api/ia`) | — | — | `src/monitoritcd/painel/http.py:211,305`; `functions/painel_api/main.py:104,172`; regras em `src/monitoritcd/painel/ia_provedores.py` | não | `material` — `alteracao_cadeia_painel` (choice) | P2 |
| 15 | UI Angular da cadeia de IA (habilitado, modelo, esforço) | — | — | `apps/painel/src/app/ia/ia.ts`, `ia.html` | não | herda #14 (gate no backend, não na UI) | P2 |
| 16 | Workflows que injetam chave de IA em execução real | — | — | `.github/workflows/monitor.yml:40-41`, `digests.yml:78`, `reprocess.yml:55-56`, `deploy-functions.yml:200,225` | não | `producao` — `producao-fim-limpo.yaml` da frota, só no fim limpo | P2 |
| 17 | Métricas de consumo de LLM (calls, tokens, falhas, % da cota) | — | — | `src/monitoritcd/metrics.py:57-62,117,141` | não | **não é gate** — é fonte do `state` de #7 e #12 | P1 |
| 18 | Regressão de prompt por snapshot | — | — | `tests/llm_regression/test_prompt_version.py` | não | `judge` — rubrica no eval de prompt (opcional) | P3 |
| 19 | Pré-filtros determinísticos que decidem o que vai ao LLM: keywords, prescore, detector temático, extractors, dedup | — | nenhum | `src/monitoritcd/filters/keywords.py`, `prescore.py`, `thematic_detector.py`, `extractors.py`, `src/monitoritcd/dedup.py` | não | `rag` — `rag_passage` só se um dia houver recuperação semântica; **hoje não encaixa** | P3 |

### Variáveis de ambiente de IA (nomes, nunca valores)

Declaradas em `src/monitoritcd/core/config.py:77-85` como `SecretStr`, opcionais em
`:36-53`, documentadas em `.env.example:17-52`:

`GEMINI_API_KEY` (única obrigatória) · `GROQ_API_KEY` · `OPENAI_API_KEY` ·
`ANTHROPIC_API_KEY` · `XAI_API_KEY` · `OPENROUTER_API_KEY` · `DEEPSEEK_API_KEY` ·
`OPENCODE_API_KEY` (reservada, sem adaptador) · `OLLAMA_BASE_URL` (sem chave, loopback).

A cadeia do painel é metadado puro — `config/painel/ia-provedores.json` guarda família,
modelo, esforço, ordem e habilitado. A chave nunca entra no JSON nem na resposta da API
(`docs/painel_ia_hml.md`, seção "Planejamento de segurança", item 5).

## 3. Lacunas

Nenhum uso de IA neste projeto passa por Jev hoje. Em ordem de valor:

1. **Saída do classificador vai direto para armazenamento e notificação.** A validação
   é estrutural (pydantic, `extra="forbid"`, allowlist de tópicos), não factual. Um
   `resumo_completo` com número de ato trocado passa pelos dois. É exatamente o caso
   `citation_check`: a afirmação está no texto coletado ou não está.
2. **`contexto` é a superfície de alucinação assumida.** O prompt autoriza conhecimento
   jurídico geral ali e proíbe inventar norma, alíquota e jurisprudência — mas nada
   verifica a proibição. O texto sai para o Telegram e o e-mail rotulado "Contexto
   (gerado por IA)" (`notifiers/templates/telegram.md.j2:16`, `email.html.j2:100`).
3. **Descrição de tópico via `/topicos` entra no system prompt.** Há defesa —
   `_prompt_data_literal` serializa como dado JSON e a regra 8 do prompt manda ignorar
   instruções embutidas — mas não há gate de entrada. É o `guardrails.allow_input`.
4. **CRITICO vira push imediato sem árbitro.** O template de frota
   `monitor-itcd-critico.yaml` foi escrito para este projeto e nunca foi ligado.
5. **Reprocessamento em massa gasta cota e sobrescreve classificação armazenada** sem
   nada tipado antes da confirmação.
6. **A escolha de provedor é estática.** A cadeia vem do painel e tenta em ordem; não há
   roteamento por custo/dificuldade do lote, ainda que `metrics.py` já tenha os números
   que alimentariam essa decisão.

## 4. Proposta de gates

Perguntas tipadas em [`docs/jev/gates/`](jev/gates) — um arquivo por gate, em inglês,
`choice.criteria` como dict, `score.criteria` como lista, `noul` com `"true"`/`"false"`,
conforme o `SCHEMA-NOTE` do stack. Os nomes das forks casam com o que `jev-act-decide.py`
procura em cada gate. Reuso, sem reinventar:

| Gate | Origem | Uso no MonitorITCD |
|---|---|---|
| `citation` | `onda2/templates/citation-check.yaml` | `gates/classificacao.yaml` — noul `supported` e score `risco_contexto` |
| `guardrails` | `onda2/templates/guardrails-io.yaml` | `gates/topico.yaml` — noul `allow_input` |
| `critico` | `templates/monitor-itcd-critico.yaml` (já existe, escrito para este projeto) | `gates/critico.yaml` — mesma choice, state deste projeto |
| `material` | `onda2/templates/model-router.yaml` | `gates/rota-provedor.yaml` e `gates/cadeia-painel.yaml` |
| `destructive` | `onda2/templates/confidence-routing.yaml` | `gates/reprocessamento.yaml` |
| `producao` | `templates/producao-fim-limpo.yaml` | workflows que publicam, só no fim limpo |
| `judge` | `onda2/templates/jev-judge.yaml` | rubrica de qualidade do prompt (P3) |

Como chamar, sem inventar mecanismo: `~/Projetos/Skill/tools/jev-eval/jev-eval.sh`
(`--backend auto`) produz o JSON; `lib/jev-act-decide.py --gate <gate>` devolve exit 0
allow / exit 2 deny. O `state` enviado carrega o texto coletado, a saída do classificador
e os números de cota — **nunca** chave de API.

### Regras que o encaixe respeita

- Jev arbitra fork tipado; não escreve resumo, ementa, alíquota nem contexto jurídico.
- Jev não substitui `RawLLMResponseV2` nem a allowlist de tópicos. Soma-se a elas.
- **Jev indisponível não para o trabalho** (founder, 2026-09-20): sem veredito, a rotina segue
  como se o Jev não existisse — sem espera, sem reconsulta em loop, sem tarefa estacionada.
  A exceção é `producao`, que nunca é autorizado por ausência de resposta.
- Nada de yolo, skip-permissions ou `git push --force` em main a partir de um score.
- Deny em `citation` ou `guardrails` **não** descarta o item: rebaixa para o digest ou
  marca para revisão. Descartar silenciosamente perderia coleta com proveniência, que é
  o produto.
- O conteúdo coletado permanece verbatim em qualquer caminho.

## 5. Plano de implementação

Plano completo, com detalhe por fase: [`docs/jev/PLANO-JEV.md`](jev/PLANO-JEV.md).
Operação da Fase 0: [`docs/jev/CALLPOINT-MONITORITCD.md`](jev/CALLPOINT-MONITORITCD.md).
Cada fase fecha com o comando canônico do `AGENTS.md` (`pytest` com cobertura ≥ 95,
`ruff check .`, `ruff format --check .`, `mypy`).

**Fase 0 — ligação em shadow (R1). Implementada em 2026-09-20.** Módulo
`src/monitoritcd/llm/jev_gate.py`: chama o helper por `subprocess`, timeout curto, opt-in por
`JEV_SHADOW=1`, teto de chamadas por processo, e apenas registra a decisão em `structlog`.
Seis callpoints instrumentados — classificação, CRITICO, rota de provedor, reprocessamento,
`/topicos` e cadeia do painel — nenhum alterando o fluxo. 43 testes cobrindo fail-open,
truncamento do state e equivalência de comportamento sob `deny`.

**Fase 1 — `citation` e `guardrails` em Act (R1).** Com a taxa de deny calibrada na
fase 0: deny em `classificacao_fundamentada` rebaixa o item para digest e grava o motivo;
deny em `entrada_segura` recusa a descrição de tópico em `/topicos` antes de ela chegar
ao prompt. Testes com provedor fake cobrindo allow, deny e Jev indisponível.

**Fase 2 — `critico` e `destructive` (R1).** Ligar `monitor-itcd-critico.yaml` antes do
push imediato e `reprocessamento_em_massa` antes de `/reprocessar` emitir o token de
confirmação. Ambos com fail-open explícito.

**Fase 3 — `material` (R1).** `rota_provedor` alimentado por `metrics.py` como advisory
sobre a cadeia do painel, e `alteracao_cadeia_painel` no `POST /api/ia`. A UI Angular não
muda: o gate fica no backend.

**Fase 4 — `producao` (R2).** Os workflows que injetam chave de IA passam pelo gate de
fim limpo. Toca CI/release, exige revisão independente e pedido expresso — fora do
alcance de qualquer sessão que não tenha essa autorização.

**Fase 5 — `judge` (R0/R1, opcional).** Rubrica no eval de prompt junto do snapshot de
`PROMPT_VERSION`, para que um bump de versão traga evidência de qualidade e não só a
quebra do snapshot.

## 6. Pendências que este inventário não resolve

- O campo `esforco` do painel (`baixo`…`maximo`) é persistido e nunca lido por
  `montar_cadeia`. Ou vira parâmetro real de chamada, ou sai do contrato. Achado
  registrado aqui, fora do escopo desta sessão.
- `OPENCODE_API_KEY` está declarada em `config.py` e no `.env.example` sem adaptador
  correspondente em `_instanciar`. Chave reservada sem uso.
- Os YAML em `docs/jev/gates/` vivem no repo para versionar junto do código que os consome.
  O catálogo de frota é `~/Projetos/Skill/compartilhado/jev-implementacao-20260919/templates/`;
  se um gate daqui virar padrão de frota, promover a cópia canônica de lá.
- O `.venv` do worktree aponta para o repo principal, então a suíte precisa de `PYTHONPATH=src`
  para exercitar o código do worktree. Sem isso, `pytest` testa o `src` do checkout principal
  e um módulo novo aparece como `ImportError`. Confirmar se o CI sofre do mesmo problema.
