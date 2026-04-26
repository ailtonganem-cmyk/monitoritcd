# Fontes alternativas para UFs sem API legislativa direta

> Investigação 2026-04-26 via WebFetch das URLs candidatas. Documento as
> opções **realmente acessíveis** (e as que não funcionam) para cada
> classe de fonte. Substitui parcialmente a coleta de proposições em
> tramitação nas 13 UFs sem API SAPL/custom: SP, RJ, SC, MA, BA, PA,
> AP, RN, MS, SE, TO, RS, DF.

## TL;DR — o que pode entrar no sistema sem custo de manutenção alto

| Prioridade | Fonte | Cobertura | Esforço |
|---|---|---|---|
| 🟢 Alta | **API Câmara dos Deputados v2** | Federal — PLs/PECs sobre ITCD afetam todos os 27 entes | 1 collector, 2-3h |
| 🟢 Alta | **API Senado novo `/processo`** (substitui legacy em fev/2026) | Federal — idem | 1 collector, 2-3h |
| 🟡 Média | **RSS ALEMS** (Mato Grosso do Sul) | Notícias diárias da assembleia — captura movimento de PLs sem precisar do form de busca | 1 fonte YAML, 30min |
| 🟡 Média | **ALMG endpoints adicionais** (já temos a API base) — Discursos, Comissões, Diário Legislativo | Enriquece cobertura MG existente | 30min cada |
| 🔴 Baixa/N | Demais 12 UFs | Continua sem API estruturada acessível | — |

## 1. Fontes federais com API pública robusta

Estes são os **maiores ganhos** — não substituem proposições estaduais,
mas cobrem reformas federais que afetam ITCD em todos os entes (PEC 45,
LC 87, LCs sobre IBS, vetos presidenciais).

### 1.1 Câmara dos Deputados — `dadosabertos.camara.leg.br/api/v2`

✅ **Validado em 2026-04-26**:

```
https://dadosabertos.camara.leg.br/api/v2/proposicoes?keywords=ITCD&itens=5
```

- Retorna JSON estruturado
- Aceita `keywords` (filtra ementa)
- Paginação via `pagina=N&itens=M`
- Sem autenticação
- Atualização diária (segundo a doc)
- Campos retornados: `id`, `siglaTipo` (PLP/PEC/PL), `numero`, `ano`,
  `ementa`, `dataApresentacao`, links HATEOAS

**Próximo passo:** criar `CamaraDeputadosCollector` análogo ao
`SAPLCollector` — fonte YAML em `sources/_federal/camara-deputados.yaml`.

### 1.2 Senado Federal — APIs em transição

Legacy: `https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista`

- ✅ XML válido, aceita `palavraChave` e `siglaSubtipo` (PLS, PEC, etc.)
- ⚠️ **Depreciada em 2026-02-01** (já passou — pode parar a qualquer hora)

Novo: `https://legis.senado.leg.br/dadosabertos/processo`

- ✅ JSON válido, retorna ementa + tipoDocumento + dataApresentacao
- 🟡 Suporte a `palavraChave` precisa ser confirmado em testes adicionais
  (não foi explicitamente demonstrado nas amostras retornadas)
- 🟡 Paginação não documentada — precisa testar `offset`/`limit`/`page`

**Próximo passo:** criar `SenadoCollector` usando `/processo` com fallback
para legacy se o novo não suportar `palavraChave` direto.

## 2. Substitutos parciais por UF — **achados utilizáveis**

### 2.1 MS (Mato Grosso do Sul) — RSS de notícias

✅ **Validado**: `https://www.al.ms.gov.br/RSS`

- RSS 2.0 válido
- Publicação diária durante sessões
- Categorias: "Direto do Gabinete", "Agência de Notícias"
- Cobre comunicados sobre PLs (não a base bruta), eventos legislativos,
  pautas de comissões.

**Limite:** notícias não substituem 100% a base de proposições. Mas captura
movimento legislativo (audiências, aprovações, vetos). Filtro por keyword
ITCD/sucessão/herança recupera os hits relevantes.

**Próximo passo:** criar `sources/MS/alems-noticias.yaml` usando o
`generic_rss` collector existente.

### 2.2 TO (Tocantins) — RSS de notícias (estrutura existe, URL específica não validada)

🟡 Site lista 5 categorias de RSS (Notícias, Legislação, Diários, Licitações,
Publicações Internas) mas a URL canônica `/rss/noticias` retornou 404 no teste.

**Próximo passo:** investigação manual para descobrir URL exata (provável
`/rss/noticia` ou `/feeds/noticias`). Se encontrada, `generic_rss` cobre.

### 2.3 ALMG — endpoints adicionais (já cobrimos legislacao + proposicoes)

✅ Portal lista categorias adicionais não usadas hoje:
- Diário do Legislativo
- Discursos / Pronunciamentos
- Comissões
- Agenda
- Votações

**Próximo passo:** decidir se vale custo de implementar para enriquecer a
cobertura MG (já forte). Não é prioridade vs. cobrir UFs sem fonte alguma.

## 3. Fontes que **NÃO funcionam** — não tente reativar sem reler isto

### 3.1 Veículos jurídicos

| Fonte | Status | Razão |
|---|---|---|
| Conjur | 🔴 HTTP 403 | Bloqueia bots; só consumo via browser |
| Migalhas | 🔴 HTTP 404 em `/migalhasrss` | URL canônica não existe; provável que tenham removido feeds |
| JOTA | ✅ já temos | RSS oficial em `https://www.jota.info/feed/` |

### 3.2 Tribunais Estaduais (TJs)

Investigado: TJSP, TJRJ, TJRS — **nenhum oferece RSS público** em 2026.
Apenas newsletter por e-mail ou consulta web. Diários eletrônicos
podem ter API via DJEN/CNJ (`comunicaapi.pje.jus.br/api/v1`) mas
retornou 403 sem autenticação.

### 3.3 Imprensa Nacional / DOU

URL: `https://www.in.gov.br/api/v1/jornal/2/secao` retornou socket closed
em testes consecutivos. **Possivelmente bloqueia bots fora de IP brasileiro**
ou exige headers específicos.

**Workaround possível**: o coletor `proxy_br` (Cloud Function em
southamerica-east1) já é usado para outras fontes geo-restritas; poderia
ser tentado aqui se houver demanda.

### 3.4 CONFAZ

Lista anual de convênios em `https://www.confaz.fazenda.gov.br/legislacao/convenios/{ano}`,
mas:
- Sem RSS / API
- Foco em ICMS — **não cobre ITCD especificamente**
- Convênios que afetam ITCD (raros, isenções entre UFs) precisariam ser
  identificados manualmente

### 3.5 ANOREG / IBDFAM / CNJ

- ANOREG: socket closed em testes; site institucional sem feeds aparentes
- IBDFAM: já listado em `README.md` como `fragile` (verificar URL)
- CNJ Provimentos: sem API pública unificada; cada provimento exige
  WebFetch dedicado

### 3.6 Assembleias estaduais sem API (confirmado por investigação)

| UF | Plataforma | Confirmação |
|---|---|---|
| **SP** ALESP | Form Struts/Java + VIEWSTATE | sem RSS canônico |
| **RJ** ALERJ | Lotus Notes legacy `/lotus_notes/` | sem dados estruturados |
| **BA** ALEBA | ECONNREFUSED em testes | provável bloqueio |
| **MA** ALEMA | ECONNREFUSED em testes | sistema desatualizado |
| **PA** ALEPA | ECONNREFUSED em testes | API existente é Whaticket (chatbot) |
| **AP** ALEAP | "eLegis em fase de implementação" | aguardar 2026-Q3+ |
| **RN** ALRN | sem RSS/API documentada | só transparência web |
| **SE** ALESE | sem RSS/API documentada | "Alese Legis" só consulta web |

## 4. Próximos passos sugeridos por valor decrescente

### Prioridade Alta — implementar (próxima sessão dedicada)

1. **`CamaraDeputadosCollector`** + YAML federal — ~3h
   - Gain: cobertura federal ITCD (Reforma Tributária, LC 87 modificações)
   - Risco: baixo (API estável, oficial, documentada)

2. **`SenadoCollector`** + YAML federal — ~3h
   - Gain: matérias originadas no Senado, vetos presidenciais
   - Risco: médio (API legacy depreciando, novo `/processo` precisa
     validação adicional de `palavraChave`)

### Prioridade Média

3. **`sources/MS/alems-noticias.yaml`** usando `generic_rss` existente — 30min
   - Gain: 1 UF a mais com sinal de movimento legislativo
   - Risco: nulo (RSS oficial validado)

4. Investigar URL exata do RSS ALETO via página oficial — 1h
   - Gain: potencialmente +1 UF (TO)
   - Risco: nulo se descoberta confirmada

### Prioridade Baixa / aguardar

5. ALEAP eLegis — monitorar evolução (talvez Q3 2026)
6. DJEN/CNJ — exige negociação de credenciais
7. SEFAZ-UF instruções normativas — sites individuais sem padrão; alto
   custo, alta fragilidade

## 5. Fontes intencionalmente descartadas

- **HTML scraping de assembleias** (Playwright/Selenium): rejeitado em
  2026-04-26 por custo de manutenção (~20 quebras/mês × 13 UFs).
- **Twitter/X via Nitter**: instâncias Nitter morreram em 2024-2025;
  apenas 1-2 ainda funcionam mas sem garantia.
- **YouTube canais oficiais via RSS auto** (`youtube.com/feeds/videos.xml`):
  feed retornou 404 nos testes para `alerjnoticias`; nomes de canais
  variam por UF — investigação caso a caso, baixo retorno.
- **Conjur via scraping**: 403 com User-Agent padrão; tentativa de
  contornar levaria a banimento de IP do GitHub Actions.

## 6. Histórico de validação

| Data | Fontes investigadas | Hits úteis |
|---|---|---|
| 2026-04-25 | Inicial — 27 UFs SAPL/custom | 14 UFs cobertas |
| 2026-04-26 | Alternativas — federais + RSS estaduais | +Câmara, +Senado, +ALEMS, +ALETO (parcial) |
