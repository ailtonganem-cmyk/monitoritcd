# 40 — Regras de negócio do domínio (MonitorITCD)

> Fonte da verdade do **domínio**: o que o sistema afirma ao dono, de onde vêm
> os fatos e o que jamais pode ser inventado. Este é um dos dois módulos
> por-projeto (o outro é o `00-identidade-projeto.md`).

## Fatos protegidos — NUNCA inventar

**NUNCA inventar fato, número, lei, alíquota, prazo, jurisprudência, número de
ato ou referência externa** exibida ao dono ou usada em classificação, resumo,
digest ou documento gerado. Diante de lacuna, a saída correta é **apontar a
fonte a consultar** — nunca um valor arbitrado. Nenhuma SPEC, colegiado ou
consenso de agentes dissolve esta regra; ela vale igualmente para o **texto que
o agente escreve** e para o **texto que o LLM do pipeline gera**.

Fatos protegidos deste domínio:

- **Alíquotas e faixas de ITCD por UF** — cada ente fixa a sua em lei estadual
  própria, com regras de progressividade distintas. O valor vigente vive em
  `docs/ufs/{UF}.md`, **com citação da lei**; nunca afirmar de memória, nem em
  código, nem em teste, nem em mensagem ao dono.
- **Números de atos** (lei, decreto, IN, portaria, PL) — só o que vem verbatim
  da fonte coletada. Ato citado sem número na fonte permanece sem número.
- **Jurisprudência** (tema repetitivo, súmula, RE/REsp) — só o que a fonte
  publicou. Proibido "lembrar" de julgado não coletado.
- **Prazos processuais e tributários** — derivam da norma citada, com referência.
- **Datas de publicação/vigência** — vêm da fonte; ausência é `null`, nunca
  estimativa.

## Domínio — 3 divisões temáticas (modeladas como `Topic`)

### ITCD (tributário)

ITCD = ITCMD = ITD: tributo estadual sobre heranças e doações, legislado por
cada UF. Fontes: assembleias legislativas, SEFAZs, diários oficiais estaduais e
LexML federal.

### Sucessões (Direito Civil — CC arts. 1.784+)

Herança, testamento, inventário judicial e extrajudicial, partilha, herdeiros
necessários, legítima, deserdação, indignidade, união estável, cônjuge
supérstite, usufruto vidual, Provimento 56/CNJ. Fontes: STF, STJ, CNJ, IBDFAM,
imprensa jurídica especializada.

### Regime de Bens (CC arts. 1.639-1.688)

Comunhão parcial e universal, separação total/obrigatória/convencional, pacto
antenupcial, alteração de regime, Súmula 377/STF, art. 1.829, aquestos,
participação final nos aquestos. Fontes: STF, STJ, IBDFAM, doutrina.

**Termos canônicos** implementados em `filters/keywords.py`, separados por
tópico: `KEYWORDS_ITCD`, `KEYWORDS_SUCESSOES`, `KEYWORDS_REGIME_BENS`,
`KEYWORDS_DEFAULT` (união). Palavra-chave nova entra no conjunto do tópico
correspondente, com teste.

## Fontes normativas canônicas

| Assunto | Fonte | Como usar |
| --- | --- | --- |
| Alíquota / regime de ITCD por UF | Lei estadual + regulamento da UF | Registrar em `docs/ufs/{UF}.md` com citação; código nunca hardcoda valor |
| Sucessões e regime de bens | Código Civil, súmulas, teses do STF/STJ | Citar artigo/tema; nunca parafrasear como se fosse texto legal |
| Atos federais consolidados | LexML | Fonte de número e ementa verbatim |
| Jurisprudência superior | RSS oficiais STF/STJ/TRFs/CNJ | Verbatim; contexto separado (ver LLM abaixo) |
| Situação de cobertura por UF | `docs/UFS_STATUS.md`, `docs/sources_status.md` | Estado real das fontes — atualizar junto com a mudança |

## Comportamento do LLM — regra crítica do produto

**Princípio inegociável: o LLM NÃO modifica conteúdo original.**

O LLM (Gemini 2.5 Flash primário; Groq fallback — ADR-0002) é usado **apenas**
para:

1. **Classificar** o tipo: `PL | Lei Sancionada | Decreto | IN | Portaria |
   Notícia | Jurisprudência | Doutrina`.
2. **Pontuar** relevância de 0 a 10 → mapeada em severity tier (`50`).
3. **Extrair** metadados: UF, número do ato, data, órgão emissor.
4. **Gerar resumo factual autossuficiente** preservando nomes, números, datas e
   cifras **verbatim** — o `resumo_completo` deve permitir entender a informação
   **sem abrir o link** da fonte.
5. **Contextualizar** (decisão do dono 2026-07-08) a legislação, jurisprudência
   e institutos citados — o que é a norma, o que muda, o significado prático —
   em campo **separado e rotulado como gerado por IA** (`contexto`).

**O LLM NÃO pode:**

- ❌ Anonimizar nomes ou substituir partes por placeholders (`[Parte]`).
- ❌ Parafrasear de forma que altere o sentido.
- ❌ Omitir, ofuscar, normalizar ou "limpar" informação.
- ❌ Inferir ou especular **dentro do resumo factual** (`resumo`/`resumo_completo`)
  — ali vale só o explícito no texto. Conhecimento jurídico geral entra
  **exclusivamente** no campo `contexto`.
- ❌ Inventar norma, número de ato, alíquota ou julgado no `contexto`. Em
  incerteza, o `contexto` **declara a limitação** em vez de especular.

### Separação estrita no schema — `original` é write-once

```
documento/{doc_id}:
  schema_version
  source:        id, uf, tipo, url
  original:      # IMUTÁVEL, write-once
    titulo_raw, texto_raw, data_publicacao, fetched_at, raw_storage_path
  llm:           # gerado por LLM, reprocessável
    classified_at, llm_model, llm_prompt_version, tipo, relevancia,
    severity_tier, resumo, resumo_completo, contexto, metadados_extraidos, tags
  notificacao:   enviada, enviada_em, canais
  status:        pending | classified | notified | archived
```

Só `llm` e `notificacao` podem ser sobrescritos. Reprocessar com prompt/modelo
novo: `python -m monitoritcd.main --reprocess --since YYYY-MM-DD [--uf MG]` —
preserva `original.*` integralmente.

**Prompt injection** é tratada como ameaça de produto, não só de segurança:
conteúdo coletado entra delimitado (`<context>…</context>`), instruções vivem no
system prompt e a saída é validada por pydantic com `extra="forbid"` (`60`).

## Regras de produto seladas (NÃO reabrir sem ordem do dono)

- **Sem backfill.** A coleta começa no go-live; o passado é passado.
- **Escopo ativo = MG + federais** (2026-07-08). Demais UFs ficam no repo,
  desativadas via Firestore.
- **Gemini é o sumarizador primário** (2026-07-08) — com escopo MG+federal o
  volume cabe na cota gratuita. Supersede a inversão de 2026-04-27.
- **Enriquecimento contextual por IA** em campo separado e rotulado (2026-07-08).
- **WhatsApp fica para fase 2**; MVP entrega em e-mail + Telegram.
- **PDF sem OCR** — `pypdf` básico; PDF escaneado é marcado
  `requires_manual_review` e o dono é notificado.
- **Idempotência:** rodar duas vezes no mesmo dia não duplica notificação.
- **Retenção:** descartados pelo LLM purgados após 90 dias; `audit_log` 1 ano;
  `execucoes` 6 meses.

## Seleção de UFs ativas — ativação é runtime, não código

O repositório carrega YAML pronto para os 27 entes desde o dia 1. A fonte da
verdade da ativação é o documento Firestore `config/active_states`
(`active_uf`, `federal_active`, `silenced_until`, `updated_at`, `updated_by`);
o seed inicial é `scripts/seed_active_states.py` (default `--ufs MG`).

- Fonte cuja UF não esteja em `active_uf` é **pulada silenciosamente**, com log INFO.
- Fontes federais coletam sempre, salvo `federal_active: false`.
- Toda mudança grava em `audit_log/` com timestamp e comando original.

**Critérios para ativar uma UF** (todos, antes de entrar na lista):

1. YAML em `sources/{UF}/` para ≥ 2 fontes (assembleia + SEFAZ ou DOE).
2. Cassette VCR em `tests/integration/test_sources_{UF}.py` passando.
3. Pelo menos 1 item real classificado em sandbox.
4. Alíquota e regime vigentes documentados em `docs/ufs/{UF}.md`, com citação.

## Adicionar uma fonte nova (workflow canônico)

1. `sources/{UF}/{tipo}.yaml` — validado por pydantic na carga; URL passa pela
   whitelist anti-SSRF (`60`).
2. Layout HTML padrão → `parser: generic_html` + seletores CSS; RSS →
   `parser: generic_rss`; lógica especial → `collectors/custom/{uf}_{nome}.py`.
3. Cassette VCR em `tests/integration/test_sources_{UF}.py`.
4. `python -m monitoritcd.main --sources {UF}/{tipo} --dry-run`.
5. Commit com a bateria de gates verde (`70`).
6. Ativar o monitoramento pelo bot: `/estados ativar {UF}` (`50`).

**Collector pronto =** YAML + `--dry-run` funcionando + cassette + 1 item real
classificado + `docs/ufs/{UF}.md` atualizado.

## Conteúdo gerado (e-mail, digest, mensagens do bot)

- Ortografia pt-BR rigorosa em todo texto gerado pelo sistema.
- Conteúdo coletado é preservado **verbatim**; formatação nunca altera o teor.
- Campo `contexto` sempre rotulado como gerado por IA na renderização (`50`).
- Mensagem de erro ao dono é genérica na superfície e completa no log
  estruturado (`60`) — nunca vaza token, URL assinada ou payload bruto.
