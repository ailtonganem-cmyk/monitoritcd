# SPEC 38 — Healthcheck por fonte (alerta em zeros consecutivos)

> SPEC de Execução ratificada (`regras/10-metodo-trabalho.md`). Única entrada
> autorizada do executor. Issue:
> https://github.com/ailtonganem-cmyk/monitoritcd/issues/38

## Identificação

- **ID / slug:** `38` · `observability-healthcheck-por-fonte`
- **Porte:** média (`regras/10` — ~10 arquivos, schema novo, superfície de bot)
- **Worktree:** worktree Orca atual `observability-healthcheck-por-fonte-alerta-quand` · branch `ailtonganem-cmyk/observability-healthcheck-por-fonte-alerta-quand`
- **Orquestrador:** Grok 4.6
- **Executor previsto:** complexo (`opus` pedido em `regras/20`; neste harness aplicar o modelo da sessão — advisory)
- **MCPs/CLIs a utilizar:** nenhum MCP obrigatório (Firebase Admin via código de teste com fake client; sem deploy). GitHub MCP já usado para ler o issue. Gates: `ruff`, `mypy`, `bandit`, `pytest` no `.venv` da worktree.

## Problema e objetivo

- **Problema:** coletor que devolve `[]` (ex.: SPA Angular em `sources/MG/doe.yaml`) não é falha — a pipeline segue e o Healthchecks.io global pinta verde. Cegueira operacional: zero items por tempo indeterminado, sem alerta.
- **Objetivo:** persistir saúde por fonte, alertar o dono no Telegram quando uma fonte **opt-in** produzir 0 items em ≥ N execuções consecutivas, e expor `/saude_fontes` no bot.

## Escopo

- **Dentro:**
  - Campo opcional `expected_min_items_per_week` no modelo `Source`.
  - Coleção Firestore `monitor_source_health/{source_id}` + métodos de storage.
  - Detector no fim de `run_pipeline`: atualiza saúde por fonte consultada; emite warning estruturado e push operacional no Telegram ao cruzar o limiar.
  - Comando bot `/saude_fontes`.
  - Testes unitários do detector (N zeros → trigger; intercalado → não) e integração/smoke com fonte que devolve `[]` por N runs.
  - Docs de contrato visível: `regras/50-saidas-notificacoes.md`, `README.md` (comando), `scripts/setup_bot_commands.py`, runbook `docs/runbooks/fonte_fora_ar.md` (sintoma de zero items, distinto de exceção).
- **Fora:**
  - Corrigir `doe.yaml` / coletor SPA (outra issue).
  - Auto-disable/reativação (`source_health.py` IDEAS #369–#370) — não misturar.
  - Substituir `observability/source_heartbeat.py` (in-memory, last_success).
  - Alterar mapeamento Documento→canal do ADR-0003 (`regras/90`: perguntar).
  - Deploy de Functions, rules, IAM, backfill em produção.
  - Mass-edit de YAMLs de fonte (opt-in é por `fragile: true` ou campo explícito).
  - Agregação semanal real de items (o campo documenta expectativa; o detector é zeros consecutivos).

## Mapa de arquivos

| Arquivo | O que muda |
| --- | --- |
| `src/monitoritcd/core/models.py` | Campo `expected_min_items_per_week: int \| None = None` em `Source` (`ge=0`, `le` via limite em `limits.py`). Método/helper de efetivo: ver system design. |
| `src/monitoritcd/core/limits.py` | `MAX_EXPECTED_MIN_ITEMS_PER_WEEK` e `DEFAULT_ZERO_RUN_ALERT_THRESHOLD = 7`. |
| `src/monitoritcd/observability/source_run_health.py` | **Novo.** Modelo `SourceRunHealth`, `effective_expected_min_items`, `apply_run_counts` (puro), constante de limiar. |
| `src/monitoritcd/observability/__init__.py` | Exportar o que for público e necessário aos testes. |
| `src/monitoritcd/storage/base.py` | `upsert_source_run_health`, `get_source_run_health`, `list_source_run_health` no Protocol. |
| `src/monitoritcd/storage/firestore_store.py` | Coleção `monitor_source_health`; `assert_owner`; datas via `_dt_to_stored`. |
| `src/monitoritcd/storage/in_memory.py` | Mesma API em RAM (testes e `--dry-run`). |
| `src/monitoritcd/orchestrator.py` | `RunReport.items_per_source: dict[str, int]`; `_collect_all` preenche (exceção = 0); após coleta, `update_source_run_health` best-effort (não derruba o run); warning + Telegram no cruzamento do limiar. |
| `src/monitoritcd/bot/handlers_extra.py` | `handle_saude_fontes` + registro em `EXTRA_HANDLERS`. |
| `src/monitoritcd/bot/handlers.py` | Listar `/saude_fontes` em `/start`/`/help`. |
| `scripts/setup_bot_commands.py` | Entrada `saude_fontes` no menu. |
| `regras/50-saidas-notificacoes.md` | Documentar o comando. |
| `README.md` | Uma linha no bloco de comandos do bot. |
| `docs/runbooks/fonte_fora_ar.md` | Sintoma: zero items consecutivos ≠ exceção. |
| `tests/unit/test_source_run_health.py` | **Novo.** Detector puro. |
| `tests/unit/test_models.py` | Campo novo, default, rejeição fora do limite. |
| `tests/unit/test_firestore_store.py` | Persistência fake client. |
| `tests/unit/test_storage_inmemory.py` | Round-trip in-memory. |
| `tests/unit/test_bot_handlers_extra.py` | Handler `/saude_fontes`. |
| `tests/unit/__snapshots__/test_firestore_schema_snapshot.ambr` | `expected_min_items_per_week` no nested `source` + snapshot do doc de saúde se houver teste novo. |
| `tests/integration/test_orchestrator.py` (ou arquivo novo `test_orchestrator_source_run_health.py`) | Smoke: fonte fragile com `[]` por N runs dispara; intercalado não. |
| `tests/unit/test_firestore_schema_snapshot.py` | Snapshot do modelo `SourceRunHealth` se persistido via pydantic. |

Não editar `source_health.py` nem `tests/unit/test_source_health.py` (outro conceito).

## System design

### O que já existe e NÃO reutilizar como se fosse isto

- `source_health.py`: health score / auto-disable por histórico booleano de **exceção**. Não vê `[]`.
- `source_heartbeat.py`: singleton in-memory; some no processo. `/status` atual nem consulta isso de fato.
- Healthchecks.io: ping global de sucesso da run. Complementar, permanece.

### Opt-in

```
effective_expected_min_items(source) -> int | None
  se source.expected_min_items_per_week is not None: retorna esse int
  senão se source.fragile: retorna 1
  senão: None  # não monitora alerta (ainda persiste o doc de saúde)
```

`expected_min_items_per_week=0` explícito = opt-out mesmo com `fragile: true`.

O valor efetivo > 0 liga o alerta de zeros consecutivos. Não implemente soma semanal nesta tarefa.

### Contrato Firestore

Coleção: `monitor_source_health` (doc id = `source_id`).

Campos:

| Campo | Tipo | Notas |
| --- | --- | --- |
| `owner_id` | str | Obrigatório (`OwnerScoped` / `assert_owner`). Ausente no enunciado; invariante de storage. |
| `source_id` | str | Igual ao doc id. |
| `last_nonzero_at` | str ISO UTC ou null | Última run com items > 0. |
| `consecutive_zero_runs` | int ≥ 0 | Zeros seguidos, inclusive exceção na coleta. |
| `last_run_at` | str ISO UTC | Última run que consultou a fonte. |
| `last_items_count` | int ≥ 0 | Extra útil; não substitui os quatro do enunciado. |

Datas: mesma convenção `_dt_to_stored` de `monitor_runs`.

`firestore.rules` já é deny-all; **não alterar**.

### Detector (função pura, fácil de testar)

Entrada: estado anterior ou `None`, `items_count: int`, `now`, `alert_threshold=7`.

- `items_count > 0`: `consecutive_zero_runs = 0`; `last_nonzero_at = now`; `alert_now = False`.
- `items_count == 0`: incrementa; `alert_now = True` **somente** se o novo valor **é igual** ao limiar (cruzamento). Se já estava ≥ limiar, não re-alerta (anti-spam).

`last_run_at = now` sempre. `last_items_count = items_count`.

Exceção em `_collect_all` conta como `items_count = 0` (fonte consultada, zero items). Fonte pulada (UF inativa, geo skip, `only_source_id`) **não** atualiza saúde.

### Orquestrador

1. `_collect_all` preenche `report.items_per_source[source.id] = len(result)` ou `0` se `BaseException`.
2. Depois da coleta (mesmo se a run depois falhar em LLM), chamar updater best-effort: falha de storage **não** derruba a run (espelhar `save_run_report`).
3. Para cada fonte com `effective_expected_min_items > 0` e `alert_now`:
   - `bound.warning("source.zero_run_threshold", source=..., consecutive=..., threshold=...)`
   - Se `notify=True` e Telegram configurado: `TelegramNotifier.send_message` com texto operacional, MarkdownV2 via `escape_markdown_v2`. Visual: `🟠` + “ALTA (operacional)”. Conteúdo: `source_id`, N, `last_nonzero_at` ou “nunca”. Sem stack, sem URL interna, sem secret.
4. **Não** criar `Documento` nem passar pelo mapeamento de severity de ato.

Isto **não** muda ADR-0003: ALTA de documento continua no digest. Este push é alerta de sistema, pedido pelo issue, fora da classificação LLM.

### Bot `/saude_fontes`

- Sem argumentos (rejeitar args extras com mensagem genérica — Princípio 1).
- Lê `list_source_run_health`.
- Lista fontes com `consecutive_zero_runs >= 1`, pior primeiro.
- Destaca as que `consecutive_zero_runs >= 7`.
- Se vazio: “Nenhuma fonte com zero items recente.”
- Escape MarkdownV2. Sem I/O Telegram no handler (só `HandlerResult`).
- Registrar em `EXTRA_HANDLERS`, `/start`, `setup_bot_commands.py`.

### Heartbeat in-memory

Opcional e **não obrigatório**: `record_source_success` / `record_source_failure` podem continuar como estão. Não use o singleton como fonte de verdade do alerta.

## Decisões e alternativas descartadas

- **Decisão:** coleção `monitor_source_health` — **porquê:** todas as coleções vigentes usam prefixo `monitor_*` (`monitor_runs`, `monitor_documentos`). — **descartado:** `source_health/` literal do issue (colide semanticamente com o módulo Python `source_health.py` e foge da convenção).
- **Decisão:** módulo novo `observability/source_run_health.py` — **porquê:** `source_health.py` já cobre IDEAS #369–#387. — **descartado:** inflar aquele arquivo.
- **Decisão:** persistir saúde de **toda** fonte consultada; alertar só opt-in — **porquê:** `/saude_fontes` precisa ver zeros também em fonte não-fragile; alerta em todas as federais geraria ruído (muitas publicam 0 na maior parte dos dias).
- **Decisão:** alerta só no cruzamento N, não em N+1… — **porquê:** anti-spam diário. Recupera com items > 0 (reset). — **descartado:** reenviar todo dia; cooldown extra (`alerted_at`) — desnecessário se o cruzamento é a regra.
- **Decisão:** push operacional imediato, visual 🟠, sem mudar ADR-0003 — **porquê:** o issue pede notificação; mudar mapeamento de Documento é `perguntar` (`90`). — **descartado:** enfileirar no digest ALTA (o digest não lista fontes vazias — a cegueira continuaria).
- **Decisão:** N=7 constante em `limits.py` — **porquê:** sugestão do issue (≈ 1 semana no cron diário). Não tornar configurável por env nesta fatia.

## Métodos e melhores práticas obrigatórias

- `regras/60`: `extra="forbid"`, `Field` com limites, `assert_owner`, datas UTC, erro genérico na superfície, detalhe no log.
- `regras/50`: escape MarkdownV2 via `security/markdown_escape.py`; split 4096 se a lista crescer; snapshot/teste do texto do handler.
- `regras/40`: nenhum fato normativo.
- `regras/70`: cobertura `core/` 100%; não skip; cassette/respx se tocar HTTP (Telegram mockado).
- `regras/80`: executor **não** usa git de escrita.
- `regras/90`: sem deploy, sem backfill em produção, sem `--no-verify`.
- Falha de uma fonte não derruba a run (já vigente) — o updater de saúde também é best-effort.
- Identificadores em inglês; comentários/docstrings pt-BR, só o porquê não-óbvio.
- Não comentar WHAT.

## Plano de execução

1. Limites + campo em `Source` + testes de modelo.
2. `SourceRunHealth` + detector puro + testes unitários (N zeros; intercalado; cruzamento único; opt-in/out).
3. Storage protocol + in-memory + firestore (fake client) + snapshot de schema.
4. Orquestrador: `items_per_source`, hook pós-coleta, warning, Telegram mockado no teste de integração.
5. Bot `/saude_fontes` + `/start` + `setup_bot_commands.py` + testes do handler.
6. Docs (`regras/50`, README, runbook).
7. Gates da seção Validação. Relatório com saída literal.

## Riscos e armadilhas

- Snapshot syrupy do `Documento.source` quebra ao adicionar campo — atualizar no mesmo trabalho.
- `InMemoryStorage` hoje **não** implementa `save_run_report`; o protocolo de saúde **deve** existir nos dois backends senão `/saude_fontes` em teste/dry-run fica cego.
- `--dry-run` usa InMemory sem seed de UFs (`70`) — o smoke de integração **não** deve depender de `doe.yaml` real nem de rede; mockar coletor/`collect_from_source`.
- `core/` exige cobertura 100% — ramos do validator e do helper efetivo precisam de teste.
- Telegram 400 por MarkdownV2 — usar `escape_markdown_v2`; teste com `source_id` contendo `_` / `-`.
- Não importar ciclo: `orchestrator` → `source_run_health` → não importar orchestrator.
- `pip install -e` desta worktree (`.venv` local). Não symlink.
- Bot webhook só vê o código após deploy — registrar pendência, não deployar.

## Critério de aceite

- [ ] `Source` aceita `expected_min_items_per_week` opcional; YAML sem o campo continua válido.
- [ ] `fragile: true` ⇒ efetivo 1; campo explícito 0 ⇒ opt-out; campo explícito N>0 ⇒ opt-in mesmo sem fragile.
- [ ] Coleção `monitor_source_health/{source_id}` com schema acordado + `owner_id`.
- [ ] N zeros consecutivos em fonte opt-in ⇒ `alert_now=True` uma vez; warning estruturado; Telegram chamado se `notify=True`.
- [ ] Zero, depois >0, depois zero ⇒ não alerta (abaixo de N).
- [ ] Fonte não opt-in com zeros: persiste, não alerta.
- [ ] `/saude_fontes` lista zeros recentes; vazio tem mensagem estável.
- [ ] Testes unitários do detector e do handler; smoke de orquestrador com coletor que devolve `[]`.
- [ ] `firestore.rules` intocado. Sem secret. Sem git de escrita pelo executor.
- [ ] Gates da validação verdes no SHA de trabalho.

## Plano de validação (gates a rodar)

No `.venv` desta worktree (`PYTHONPATH` implícito pelo `pip install -e`):

```bash
.venv/bin/ruff check src/monitoritcd/core/models.py src/monitoritcd/core/limits.py src/monitoritcd/observability src/monitoritcd/storage src/monitoritcd/orchestrator.py src/monitoritcd/bot scripts/setup_bot_commands.py tests/unit/test_source_run_health.py tests/unit/test_models.py tests/unit/test_firestore_store.py tests/unit/test_storage_inmemory.py tests/unit/test_bot_handlers_extra.py tests/integration/test_orchestrator.py tests/unit/test_firestore_schema_snapshot.py
.venv/bin/ruff format --check src/monitoritcd tests scripts/setup_bot_commands.py
.venv/bin/mypy src/monitoritcd/core src/monitoritcd/filters src/monitoritcd/notifiers src/monitoritcd/security
.venv/bin/bandit -r src/ -ll
.venv/bin/detect-secrets scan --baseline .secrets.baseline
.venv/bin/pytest tests/unit/test_source_run_health.py tests/unit/test_models.py tests/unit/test_firestore_store.py tests/unit/test_storage_inmemory.py tests/unit/test_bot_handlers_extra.py tests/unit/test_firestore_schema_snapshot.py tests/integration/test_orchestrator.py -q --tb=short
.venv/bin/pytest --cov=src/monitoritcd --cov-branch --cov-report=term-missing --cov-fail-under=95
```

Se o arquivo de integração novo existir, incluí-lo no `pytest` focal no lugar de (ou além de) `test_orchestrator.py`.

## Evidência exigida no relatório

- Saída literal (exit code + trecho final) de ruff, mypy, bandit, detect-secrets, pytest focal e pytest cobertura.
- Lista de arquivos alterados.
- Confirmação de que o teste de N zeros falha se o incremento/cruzamento for removido (prova de mutação informal: descrever o caso; se fácil, um assert que quebra sem o detector).
- Suposições e questões separadas no ESTADO.

## Registro do R (revisão do plano)

Fuross atacados antes de despachar:

1. **Nome `source_health` colide** com módulo IDEAS → coleção `monitor_source_health` + módulo `source_run_health.py`.
2. **ALTA no ADR é digest, issue pede push** → push operacional fora do mapeamento de Documento; não alterar `50`/`0003` de canal de ato.
3. **Alertar todas as fontes** geraria ruído federal → opt-in `fragile` / campo; persistência ampla.
4. **Re-alerta diário após N** → só cruzamento.
5. **Smoke com `doe.yaml` real** viola `--dry-run`/rede/`70` → mock de coletor `[]`.
6. **Rules/IAM** → deny-all já cobre; não editar rules (EAW recusa deploy/rules).
7. **`save_run_report` fora do Protocol** → saúde entra no Protocol + InMemory para o bot funcionar em teste.
8. **NUNCAs:** sem fato normativo, sem secret, sem delete em massa, sem git write no executor, sem concluir vermelho.

SPEC ratificada pelo orquestrador em 2026-09-13. Executor: implementar com fidelidade; ambiguidade residual → interpretação razoável + linha no ESTADO.
