# IDEAS_TRIAGE.md — Triagem inicial pós-MVP

> Proposta de priorização das 500 ideias de [IDEAS.md](IDEAS.md), feita após
> conclusão das Fases 0-10 e do plano de validação A-D (2026-04-26).
>
> **Como usar**: dono marca `[x]` nos itens que quer absorver. Cada item marcado
> vira issue com label `idea-absorbed`. Fase 11 do PLAN.md absorve esses na cadência
> que o dono definir (semanal/mensal).
>
> **Não-goal**: implementar tudo. Esta lista é o "cardápio prioritário" — itens não
> listados aqui ficam no IDEAS.md para revisitar em triagens futuras.

---

## 🚀 Tier 1 — Quick wins (1-3h cada, alto valor visível)

Itens que melhoram a UX/operação do sistema com pouco código novo.

- [ ] **#100** Digest diário configurável (horário via env) — já tem `/relatorio`,
      falta envio automático no horário. Reusa template existente.
- [ ] **#103** Ranking dos itens mais relevantes da semana no digest — agrega
      por relevância LLM, top 5 destaque visual.
- [ ] **#176** Comando `/exportar csv [periodo]` — exporta docs do período
      para CSV via DM Telegram (anexo). Útil pra análise off-line.
- [ ] **#197** Stats por UF no `/status` — adiciona quebra "documentos por UF
      últimos 7 dias" ao output atual.
- [ ] **#283** Watch list com notif **imediata** em match — hoje notifica no
      próximo cron; melhorar para disparar `/notify_watch` no fim do pipeline.
- [ ] **#310** Correlation ID em logs ponta-a-ponta — já existe `run_id`,
      propagar para notifier/bot/audit (facilita debugging).
- [ ] **#348** Métrica de cota LLM restante no `/status` — Gemini tem 1500/dia;
      mostrar quanto sobrou. Detecta quota bursts.
- [ ] **#129** Botão "marcar útil/inútil" via inline keyboard Telegram — feedback
      do dono retroalimenta scoring (não retreina LLM, mas tags pessoais).
- [ ] **#46** Detecção automática de feed mudou (Last-Modified/ETag) — economiza
      bandwidth e cota LLM evitando reprocessamento de feeds estáveis.

## 🏗️ Tier 2 — Strategic (3-15h, capacidade nova)

Itens que mudam o que o sistema sabe fazer.

- [ ] **#34** Coletor Receita Federal — atos relacionados a sucessão/doação.
      Federal, complementa STF/STJ/CONFAZ.
- [ ] **#35** Coletor CONFAZ — convênios/protocolos. Crítico para ITCD
      (regula alíquotas mínimas/máximas entre estados).
- [ ] **#66** Detecção de revogação (`"revoga a Lei X"`) + cross-reference no doc.
      Permite alertas "sua norma X foi revogada hoje".
- [ ] **#85** Tracking de PEC sobre ITCD federal (unificação nacional) — identifica
      e prioriza PECs que afetariam todos os 27 estados.
- [ ] **#421** Reprocessamento via bot (`/reprocessar [periodo]`) — comando para
      reclassificar com prompt novo. CLI já existe; falta wire no bot.
- [ ] **#390** Mute por tópico jurídico (não só UF) — `/silenciar topico=sucessoes 7d`.
      Útil quando dono está focado em só uma área.
- [ ] **#258** Busca full-text com BM25 no histórico (sem dep externa pesada,
      via SQLite FTS5 local ou índice inverter Python).
- [ ] **#340** Honeytokens em arquivos do repo — alerta imediato em uso (já
      mencionado no CLAUDE.md como "fase 2").

## 🔧 Tier 3 — Polish & operacional (1-5h)

Aumentam confiabilidade ou experiência operacional.

- [ ] **#412** Backup mensal cifrado com `age` + retenção 12 — já existe schedule;
      validar que está funcionando E que restore funciona.
- [ ] **#466** VCR cassettes para mais collectors — aumenta robustez de CI
      sem chamar net real.
- [ ] **#356** Dashboard com séries temporais (volumes diários nos últimos 30d).
      Estende `build_dashboard.py`.
- [ ] **#368** Comando `/healthcheck` que testa cada fonte ativa e reporta
      latência/erro. Diagnóstico rápido sem ver logs.
- [ ] **#487** README com seção "Como adicionar uma fonte nova" passo-a-passo
      (atualmente só CLAUDE.md tem isso).

## ❌ Não recomendado agora (esforço alto, valor incerto)

Items que valem postpor para triagem futura.

- **#58** Topic modeling com BERTopic — adiciona dep pesada (sklearn+sentence-transformers),
  benefício duplica o que `topics` do LLM já faz.
- **#104, #105** Gráficos PNG base64 inline / PDF anexo via WeasyPrint — adiciona
  deps gráficas (matplotlib + weasyprint+cairo), e-mail texto serve.
- **#1-#27 (parcial)** 12 UFs restantes sem API/RSS — fonte alternativa via PDF
  scraping/OCR; esforço alto por UF, ganho marginal (estados pequenos). Já temos
  re-verificação trimestral monitorando se aparecem APIs.
- **#67** Grafo de citações entre normas — bonito mas sem caso de uso claro hoje.
  Reabrir se dono começar a precisar para análise específica.

---

## Plano de absorção sugerido

1. **Sprint 1 (semana 1)** — 3 quick wins do Tier 1 (escolha do dono).
2. **Sprint 2 (semana 2-3)** — 1 strategic do Tier 2.
3. **Sprint 3+ (mensal)** — alternar polish + strategic conforme demanda.

Cada sprint = 1 PR consolidado com testes (cobertura ≥ 95%).

**Próximo passo**: dono marca `[x]` em até 3 itens do Tier 1 e 1 item do Tier 2
para iniciar Sprint 1.
