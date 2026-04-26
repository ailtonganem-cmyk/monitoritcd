# Postmortem Template — MonitorITCD

Template baseado em [SRE postmortem template](https://sre.google/sre-book/example-postmortem/).
Use para incidentes (falha persistente do cron, deletion acidental, vazamento de secret, etc.).

---

# Incidente: [TÍTULO BREVE — ex: "ALESP indisponível por 3 dias"]

| Campo | Valor |
|---|---|
| **Data** | YYYY-MM-DD |
| **Severidade** | P1 / P2 / P3 / P4 |
| **Duração** | XXh YYmin |
| **Detectado por** | cron / monitoring / dono manualmente |
| **Resolvido por** | rollback / fix / etc. |
| **Status** | Resolved / Mitigated / Open |

## Sumário

[2-3 frases descrevendo o que aconteceu, impacto, e como foi resolvido.]

## Impacto

- **Usuários afetados**: dono (1)
- **Dados perdidos**: [N docs / 0]
- **Funcionalidade degradada**: [coleta / notificação / bot]
- **SLO breach**: [Sim / Não]

## Linha do tempo

Todos os horários em UTC.

| Horário | Evento |
|---|---|
| YYYY-MM-DD HH:MM | Início real do incidente (event 0) |
| YYYY-MM-DD HH:MM | Detecção pelo cron / alerta |
| YYYY-MM-DD HH:MM | Investigação iniciada |
| YYYY-MM-DD HH:MM | Causa raiz identificada |
| YYYY-MM-DD HH:MM | Mitigação aplicada |
| YYYY-MM-DD HH:MM | Resolução completa |

## Causa raiz

[Análise factual da causa. Não buscar culpados; buscar fatores contribuintes.]

### Fatores contribuintes

- Fator técnico A: ...
- Fator de processo B: ...
- Fator humano C (raro): ...

## Detecção

Como foi detectado? Quanto tempo demorou? Funcionou como esperado?

## Resposta

Linha de ações tomadas. O que foi tentado primeiro e falhou? O que funcionou?

## Recuperação

Tempo entre detecção → mitigação → resolução. Houve regressões?

## Lições aprendidas

### O que funcionou bem

- ...

### O que deu errado

- ...

### Onde tivemos sorte

- ...

## Action items

| Ação | Responsável | Prioridade | Prazo |
|---|---|---|---|
| Adicionar healthcheck X | dono | P2 | YYYY-MM-DD |
| Documentar runbook Y | dono | P3 | YYYY-MM-DD |

## Referências

- [Issue tracker]
- [Logs relevantes]
- [Commits de fix]
- [PRs]
