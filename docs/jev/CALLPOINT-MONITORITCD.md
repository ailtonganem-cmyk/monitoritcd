# Callpoint Jev — MonitorITCD

Data: 2026-09-20. Fase 0 (**shadow**) implementada. Fases 1+ pendentes.
Inventário que originou este trabalho: [`../JEV-IA-INVENTARIO.md`](../JEV-IA-INVENTARIO.md).

## Regra que manda sobre todas as outras

**Jev indisponível não para o trabalho.** Decisão do founder em 2026-09-20. Jev fora do ar,
sem chave, com timeout, com erro de rede ou com resposta inválida: a rotina segue exatamente
como seguiria se o Jev não existisse. Nada é adiado, nada é degradado, nada é marcado como
pendente por causa disso.

No código isso é `DecisaoJev.bloqueia` (`src/monitoritcd/llm/jev_gate.py`), que só é verdadeiro
num `deny` **explícito e efetivamente recebido**. `desligado`, `indisponivel` e `erro` nunca
bloqueiam. Qualquer fase futura deve consultar essa propriedade em vez de comparar strings.

Exceção única, herdada do contrato da frota: no gate de produção, ausência de veredito significa
**seguir sem liberar produção** — nunca liberar por omissão. Esse gate não existe neste projeto
ainda (Fase 4).

## Estado atual: Fase 0, shadow

Desligado por padrão. Só roda com `JEV_SHADOW=1`. Nenhum callpoint altera o fluxo: todos
registram a decisão em `structlog` sob o evento `jev.shadow` e seguem.

| Gate | Stem | Callpoint | Quando dispara |
|---|---|---|---|
| `citation` | `classificacao` | `orchestrator._jev_shadow_classificacao` (via `classify_and_store`) | cada item classificado que não foi descartado |
| `critico` | `critico` | idem | quando o tier efetivo é CRITICO (push imediato) |
| `material` | `rota-provedor` | `orchestrator.classify_and_store` | uma vez por execução da pipeline |
| `destructive` | `reprocessamento` | `orchestrator.reprocess_documents` | uma vez por reprocessamento |
| `guardrails` | `topico` | `bot.handlers._topicos_adicionar` | ao adicionar tópico via `/topicos` |
| `material` | `cadeia-painel` | `painel.ia_provedores.gravar` | ao persistir nova cadeia (`POST /api/ia`) |

Perguntas tipadas em `docs/jev/gates/*.yaml`, em inglês, schema conforme o `SCHEMA-NOTE` da
frota. Os nomes das forks foram escolhidos para casar com o que `jev-act-decide.py` procura:
`supported` no gate `citation`, `allow_input` no `guardrails`, `critico_vs_digest` no `critico`,
`route` e `material_fork` nos demais.

## Como ligar

```bash
export JEV_SHADOW=1
export TYPESAFE_API_KEY="$(tr -d ' \n\r\t' < ~/Projetos/APIs/jev.txt)"
python -m monitoritcd.main run --dry-run
```

Variáveis de ajuste, todas opcionais:

| Variável | Default | Efeito |
|---|---|---|
| `JEV_SHADOW` | vazio (off) | `1`, `true`, `on` ou `sim` ligam o shadow |
| `JEV_SHADOW_TIMEOUT_SECONDS` | `8` | timeout por consulta |
| `JEV_SHADOW_MAX_CALLS` | `20` | teto de consultas por processo |
| `JEV_GATES_DIR` | `docs/jev/gates` do repo | diretório dos YAML |
| `JEV_EVAL_SH` | `~/Projetos/Skill/tools/jev-eval/jev-eval.sh` | helper |
| `JEV_DECIDE_PY` | `.../jev-implementacao-20260919/lib/jev-act-decide.py` | decisor |
| `JEV_BACKEND` | `auto` | repassado ao helper |

## Como ler o resultado

Cada consulta emite uma linha `jev.shadow` com `gate`, `decisao`, `motivo`, `choice`,
`confianca`, `duracao_ms`, `divergente` e o callpoint. Para calibrar a Fase 1, o que interessa
é a taxa de `divergente=true` por gate:

```bash
JEV_SHADOW=1 python -m monitoritcd.main run --dry-run 2>&1 \
  | grep '"event": "jev.shadow"' \
  | python -c "import sys,json,collections
c=collections.Counter()
for l in sys.stdin:
    try: d=json.loads(l)
    except ValueError: continue
    c[(d.get('gate'), d.get('decisao'), d.get('motivo'))] += 1
for k,v in c.most_common(): print(v, k)"
```

Critério para promover um gate a Act (Fase 1): divergência estável e **explicável** — cada deny
amostrado precisa corresponder a um erro real do classificador. Divergência alta sem causa
identificada significa prompt do gate mal calibrado, não classificador errado.

## O que sai da máquina

O `state` enviado carrega trecho do texto coletado (conteúdo público, com proveniência) e a
saída do classificador. Cada campo é truncado em 1200 caracteres e achatado em uma linha.

Nunca sai: chave de API de nenhum provedor, credencial, cookie de sessão do painel, conteúdo de
`.env`, `OWNER_ID` ou identificador de usuário. O ambiente repassado ao helper é uma allowlist
curta (`HOME`, `PATH`, `LANG`, `TYPESAFE_API_KEY`, `JEV_BACKEND`, `JEV_SESSION_TIER`) — as chaves
de LLM do MonitorITCD ficam de fora por construção, não por disciplina.

Isso é um egress novo em relação ao que o projeto fazia. É a razão de o shadow ser opt-in.

## Limites

- Jev não escreve resumo, ementa, alíquota, contexto jurídico nem qualquer conteúdo de produto.
- Jev não substitui `RawLLMResponseV2` (`extra="forbid"`) nem a allowlist de tópicos. Soma-se.
- Jev nunca desbloqueia yolo, skip-permissions ou force-push. `yolo_by_jev` não é lido.
- Um deny futuro em `citation` ou `guardrails` rebaixa para digest ou recusa a entrada; **não**
  descarta item coletado em silêncio — a coleta com proveniência é o produto.

## Testes

- `tests/unit/test_jev_gate.py` — fail-open em toda falha, teto de chamadas, truncamento do
  state, e a tabela que fixa `bloqueia`/`indisponivel` por decisão.
- `tests/unit/test_jev_callpoints.py` — cada callpoint consulta o gate certo, e um `deny` em
  shadow não muda o resultado da função.
