# Status das fontes (atualizado 2026-04-25 — pós-LexMLPortal)

## ✅ Cobertura atual (validada em produção)

### Federais (5 fontes)
| Fonte | Cobertura | Volume típico |
|---|---|---|
| **LexML Legislação** | Federal + 27 estaduais + DF | ~56 hits ITCMD, deduped por URN |
| **LexML Jurisprudência** | STF + STJ + TJs estaduais | ~21 hits ITCMD |
| **JOTA principal** | Notícias jurídicas tributárias | ~25 entries diárias |
| **STF notícias** | Decisões STF | ~10 entries |
| **STJ notícias** | Decisões STJ | ~100 entries |

### Proposições estaduais em tramitação (14 UFs)

#### Via ALMG (custom, API JSON própria — 1 UF)
- **MG** — `dadosabertos.almg.gov.br` (proposições + legislação mineira)

#### Via SAPL/Interlegis (genérico, API REST padronizada — 11 UFs)
Validados em smoke test 2026-04-25: 104 items reais coletados:
- **AC** — `sapl.al.ac.leg.br` (4 hits ITCMD)
- **AL** — `sapl.al.al.leg.br` (PL 1334/2025)
- **AM** — `sapl.al.am.leg.br`
- **CE** — `www.al.ce.leg.br/sapl`
- **ES** — `www.al.es.leg.br/sapl`
- **GO** — `www.al.go.leg.br/sapl`
- **MT** — `sapl.al.mt.leg.br`
- **PB** — `sapl.al.pb.leg.br` (20 items)
- **PI** — `sapl.al.pi.leg.br` (12 items)
- **RO** — `sapl.al.ro.leg.br` (10 items)
- **RR** — `sapl.al.rr.leg.br` (17 items)

**Marcados inativos** (path `/sapl/api/` é WordPress, não SAPL real):
- ⚠️ **PE** — Alepe usa CMS próprio, URL `/sapl/api/` retorna HTML
- ⚠️ **SC** — Alesc idem

**Total**: 17 fontes ativas. Cobertura legislativa (LexML) atinge 27 entes + federal.
Cobertura de proposições em tramitação: 12 UFs (44%).

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

## ⛔ Proposições estaduais não cobertas (13 UFs)

Investigado em 2026-04-25, sem API REST/SAPL pública identificada:

| UF | Status | Nota |
|---|---|---|
| AP | Sem SAPL | Investigação adicional necessária |
| BA | TIMEOUT | `alba.ba.gov.br` lento ou geo-restrito |
| DF | 404 | `cl.df.gov.br` sem SAPL; investigar API própria |
| MA | 404 | `al.ma.leg.br` sem SAPL detectado |
| MS | TIMEOUT | `al.ms.gov.br` lento |
| PA | TIMEOUT/404 | ALEPA com portal próprio |
| PR | TIMEOUT | `assembleia.pr.leg.br` lento |
| RJ | 302 | ALERJ usa Lotus Notes legado |
| RN | TIMEOUT | `al.rn.leg.br` |
| RS | HTML | AL/RS tem portal HTML, sem API JSON |
| SE | TIMEOUT | `al.se.leg.br` |
| SP | Form-based | ALESP exige VIEWSTATE/AJAX |
| TO | TIMEOUT | `al.to.leg.br` |

Para essas UFs, **leis sancionadas continuam cobertas via LexML** (legislação
publicada no DOE estadual é indexada pelo Senado). A lacuna é apenas
**proposições em tramitação** que ainda não viraram lei.

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
