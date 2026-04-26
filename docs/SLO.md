# SLO — Service Level Objectives

> Sugestão #29 — define metas de serviço explícitas. SLOs são contratos com você
> mesmo: documentar alvos torna possível medir saúde objetivamente em vez de
> "parece que está ok".

## Princípio

MonitorITCD é **single-user, best-effort**. Não há SLA externo (não há cliente
pagando). Mas SLOs internos disciplinam decisões: "vale a pena reativar a UF X?
Sua taxa de sucesso ficou em Y%, abaixo do SLO."

## SLOs ativos

### S1 — Disponibilidade do cron diário

- **SLI**: % de execuções diárias que completam sem `cli.run.no_sources` e sem
  `cli.run.all_sources_failed` em janelas de 30 dias.
- **Alvo**: ≥ **95%** (ou seja: ≤ 1.5 dias com falha completa por mês).
- **Medição**: Healthchecks.io grace period + log do orquestrador.
- **Ação se violado**: análise de causa raiz nos logs do GH Actions; possível
  desativação da fonte mais flaky.

### S2 — Latência da execução

- **SLI**: tempo entre `cli.run.start` e `cli.run.done`, p95 em 30 dias.
- **Alvo**: ≤ **25 minutos** (timeout do workflow é 30 min).
- **Medição**: `RunReport.duration_seconds` em logs estruturados.
- **Ação se violado**: avaliar paralelismo (atualmente já `asyncio.gather`),
  considerar reduzir lista de fontes.

### S3 — Taxa de sucesso por fonte

- **SLI**: % de execuções em que cada fonte retorna ≥ 0 itens (sem exception).
- **Alvo**: ≥ **90%** por fonte ativa em 30 dias.
- **Medição**: `report.failed_sources` agregado.
- **Ação se violado**: três opções por ordem de preferência:
  1. Investigar e corrigir (parser quebrou, layout mudou).
  2. Marcar como `fragile: true` no YAML (reduz prioridade no scoring).
  3. Desativar via `/silenciar UF` se permanente.

### S4 — Notificação ao dono

- **SLI**: % de itens com `severity_tier=CRITICO` notificados em ≤ 5 min do
  `classified_at`.
- **Alvo**: ≥ **99%**.
- **Medição**: `documento.notificacao.enviada_em - documento.llm.classified_at`.
- **Ação se violado**: Telegram bot pode estar indisponível; verificar webhook.

### S5 — Quota LLM

- **SLI**: % de execuções que conseguem classificar **todos** os items
  pré-aprovados (sem cair em DLQ por quota).
- **Alvo**: ≥ **98%**.
- **Medição**: `report.errors` contendo `classify_deferred`.
- **Ação se violado**: revisar pré-filtro (keywords + prescore); considerar
  bump de quota Gemini ou aumento do batch size.

## SLO budget

Budget de violação = (1 - alvo) × período. Para S1:
- Alvo 95%, período 30 dias → budget = 1.5 dias/mês.
- Se gastar tudo em 10 dias do mês: pausar mudanças não-críticas até final do mês.

## Observabilidade

Métricas em formato Prometheus textfile via `monitoritcd.observability.prometheus_textfile`.
Em VPS futuro, `node_exporter` lê automaticamente.

## Revisão

Reavaliar trimestralmente:
- Os alvos atuais ainda são realistas?
- Sites .gov.br ficaram mais ou menos confiáveis?
- Devo adicionar SLO para algo que está falhando silenciosamente?
