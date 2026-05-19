# MG — Minas Gerais

## Tributo
- **Nomenclatura**: ITCD
- **Lei principal**: Lei 14.941/2003 (alterada por leis posteriores)
- **Alíquota**: 5% **fixa**

## Particularidades
- Disputa frequente sobre base de cálculo (valor de mercado vs valor venal).
- TJMG consolidou várias teses sobre ITCD em planejamento sucessório.
- ALMG tem dados abertos relativamente bem estruturados.

## Fontes mapeadas
- `almg.yaml` — proposições em tramitação. **Ativa** (parser `almg` via dadosabertos.almg.gov.br; geo_restricted=true → roda via proxy_br).
- `almg-legislacao.yaml` — leis sancionadas. **Ativa** (mesmo parser; geo_restricted=true).
- `sefaz.yaml` — atos normativos SEFAZ-MG. **Ativa** (`generic_html`; geo_restricted=true).
- `doe.yaml` — IOF/MG (Jornal Minas Gerais). **Reescrita 2026-05-19** (`iof_mg` parser custom — API REST .NET + PKCS#7 unwrap + pypdf; filtra atos com menção a SEFAZ-MG via `org_mentions` + `keywords_bypass=true`).
- `tjmg.yaml` — Tribunal de Justiça. **Reativada 2026-05-09** (RSS `/data/rss/noticiasTJMG.xml`; `geo_restricted=true` → exige worker local Windows porque proxy_br também é bloqueado).

## Status
4 das 5 fontes coletam via proxy_br (Cloud Function southamerica-east1).
TJMG é o único caso "exclusivo do worker local" — TJMG bloqueia ranges de
IPs de cloud, não só geo. O worker local Windows roda
`monitoritcd run --only-geo-restricted` via Task Scheduler
(`scripts/install_local_monitor_task.ps1`).

Se o worker local não estiver rodando, TJMG falhará isolada (não derruba
pipeline) e MG segue coberto pelas outras 4 fontes via proxy_br.

## Referências externas
- ALMG: https://www.almg.gov.br/
- SEFAZ-MG: https://www.fazenda.mg.gov.br/
- Jornal Minas Gerais: https://www.jornalminasgerais.mg.gov.br/
- TJMG: https://www.tjmg.jus.br/
- Dados Abertos ALMG: https://dadosabertos.almg.gov.br/

## API do IOF/MG (descoberta 2026-05-19)

Base: `https://www.jornalminasgerais.mg.gov.br/api/v1/`

| Endpoint | Auth | Resposta |
|---|---|---|
| `POST /Autenticacao/Autenticar` (body `{}`) | nenhuma | JWT anônimo (sub=`usuarioPortal`, exp ~2h) |
| `GET /Jornal/ObterUltimaEdicaoECalendarioParaHome` | nenhuma | IDs dos cadernos do dia |
| `GET /Jornal/ObterEdicaoPorId/{id}` | nenhuma | `secoes[]` com `(descricao, paginaInicial)` |
| `GET /Caderno/ObterArquivoCadernoPorId?id={id}` | Bearer JWT | `{dados:{arquivo:"<base64 do PKCS#7>"}}` |

PDF interno é assinado pela cadeia ICP-Brasil (CMS SignedData). Coletor `iof_mg` extrai bytes do PDF buscando `%PDF-` / `%%EOF` no envelope decodificado. Validação criptográfica da assinatura fica como melhoria futura.
