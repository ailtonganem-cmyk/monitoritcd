# Status das fontes (atualizado 2026-04-25 — pós-LexMLPortal)

## ✅ Cobertura atual (validada em produção)

| Fonte | Cobertura | Volume típico |
|---|---|---|
| **LexML Legislação** | Federal + 27 estaduais + DF | ~56 hits ITCMD, deduped por URN |
| **LexML Jurisprudência** | STF + STJ + TJs estaduais | ~21 hits ITCMD |
| **JOTA principal** | Notícias jurídicas tributárias | ~25 entries diárias |
| **STF notícias** | Decisões STF | ~10 entries |
| **STJ notícias** | Decisões STJ | ~100 entries |
| **ALMG proposições** | MG (PLs, PECs, mensagens) | ~13 hits/run |
| **ALMG legislação** | MG (Leis sancionadas) | parte dos 13 |

**Total**: 7 fontes ativas. Cobertura de 27 estados + DF + federal via LexML.

## 🎯 Após implementação do LexMLPortalCollector

LexML Brasil indexa atos normativos de **todos os 27 entes federativos** via
URNs estruturadas:
```
urn:lex:br;sao.paulo:estadual:lei:2000-12-28;10705
urn:lex:br;rio.grande.do.sul:estadual:lei:2025-...
urn:lex:br;rio.de.janeiro:estadual:decreto:2024-...
urn:lex:br;federal:lei:1973-01-11;5172
```

Resultado: **uma única fonte (LexML) cobre legislação sancionada em todos
os entes**, sem precisar de scraper estadual individual.

## ⛔ O que LexML NÃO cobre (tradeoffs aceitos)

1. **Proposições em tramitação estaduais (PLs ainda não votados)**
   - Para MG: temos ALMG (cobre)
   - Para SP: ALESP exige scraping de form com VIEWSTATE/AJAX (frágil)
   - Para RJ/RS/DF: similar, requer collectors customizados

2. **Atos infralegais SEFAZ específicos** (resoluções, portarias internas que
   não vão ao DOE em formato pesquisável)
   - Mitigação: maioria dos atos relevantes (modificadores de alíquota,
     IN sobre bem específico) é publicada via DOE-estadual e aparece no
     LexML após indexação.

3. **Notícias de TJs estaduais** (vs. acórdãos)
   - Acórdãos: LexML cobre
   - Notas/comunicados: precisam RSS específico (TRFs/TJs em geral
     desativaram seus RSS)

## 📋 Próximos passos por valor decrescente

### Imediato (já entregue)

- [x] LexMLPortalCollector destrava 27 estados + DF + federal
- [x] ALMG já cobre proposições MG
- [x] proxy_br BR resolve geo-restrição (LexML, ALMG)

### Curto prazo — proposições estaduais (se for prioritário)

- [ ] **ALESP-PL**: scraper específico (VIEWSTATE) — ~3h
- [ ] **ALERJ-PL**: investigar API (similar ALMG?) — ~2h
- [ ] **AL/RS-PL**: scraper específico — ~3h
- [ ] **CL-DF**: investigar API + URL atual — ~2h
- [ ] **ALESP-novos eventos**: monitor RSS de notícias da casa? — ~1h

### Médio prazo — qualidade de jurisprudência

- [ ] TJSP/TJRJ/TJMG decisões via JusBrasil API (se disponível)
- [ ] Súmulas STJ específicas sobre ITCMD via API STJ-Bibliotec
- [ ] Provimentos CNJ sobre cartórios (Provimento 56/2016 e variações)

### Baixo valor

- [ ] DOEs estaduais — ASP.NET com VIEWSTATE (complexo, pouca ROI dado LexML)
- [ ] OCR de PDFs escaneados — fora do MVP

## Decisões técnicas

**Por que não scraper ALESP individual agora**: LexML já cobre Leis SP
sancionadas (a Lei do ITCMD em SP, Lei 10.705/2000, está indexada). O
delta seria apenas proposições EM TRAMITAÇÃO. Custo (3h dev + manutenção
de scraper frágil) vs. benefício (visibilidade de PLs antes de votação)
não justifica ainda. Se o dono quiser PRO-ATIVA monitoração de PLs SP
em tramitação, abrir issue.

**Por que LexML é geo_restricted=true**: servidor `lexml.gov.br` rejeita
ConnectTimeout para IPs Azure US do GitHub runner. Fallback automático
via Cloud Function `proxy_br` (BR) resolve. Em produção: já validado
funcionando 2026-04-25.
