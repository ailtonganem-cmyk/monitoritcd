# Status das 27 UFs (Sugestão #42)

> Tabela consolidada do estado de cada UF: ativa em produção, pronta-para-ativar
> (YAMLs no repo mas inativa via `active_states`), ou sem fontes mapeadas ainda.

Atualizar a cada PR que toca em `sources/{UF}/` ou em `config/active_states.default.yaml`.

## Legenda

- ✅ **Ativa** — coleta diária acontecendo.
- 🟡 **Pronta** — YAMLs prontos, ativação por bot `/estados ativar UF`.
- ⚪ **Mapeada** — YAML existe mas faltam testes/cassettes.
- ❌ **Sem fonte** — pesquisar e adicionar fontes.

## Tabela

| UF | Estado | Status | Fontes mapeadas | Doc UF | Notas |
|---|---|---|---|---|---|
| AC | Acre | 🟡 | sapl-proposicoes | — | Re-verificação trimestral |
| AL | Alagoas | 🟡 | sapl-proposicoes | — | |
| AP | Amapá | 🟡 | sapl-proposicoes | — | Re-verificação trimestral |
| AM | Amazonas | 🟡 | sapl-proposicoes | — | |
| BA | Bahia | 🟡 | portal, tjba | — | Re-verificação trimestral |
| CE | Ceará | 🟡 | sapl-proposicoes, tjce | — | |
| DF | Distrito Federal | ✅ | cldf, doe, sefaz | [DF.md](ufs/DF.md) | MVP |
| ES | Espírito Santo | 🟡 | sapl-proposicoes | — | |
| GO | Goiás | 🟡 | sapl-proposicoes | — | |
| MA | Maranhão | 🟡 | sapl-proposicoes | — | Re-verificação trimestral |
| MT | Mato Grosso | 🟡 | sapl-proposicoes | — | |
| MS | Mato Grosso do Sul | 🟡 | alems-noticias | — | |
| MG | Minas Gerais | ✅ | almg, almg-legislacao, doe, sefaz, tjmg | [MG.md](ufs/MG.md) | MVP, geo-restricted |
| PA | Pará | 🟡 | portal | — | Re-verificação trimestral |
| PB | Paraíba | 🟡 | sapl-proposicoes | — | |
| PR | Paraná | 🟡 | alep-proposicoes, tjpr | — | HTTP allowlist |
| PE | Pernambuco | 🟡 | sapl-proposicoes, tjpe | — | |
| PI | Piauí | 🟡 | sapl-proposicoes | — | |
| RJ | Rio de Janeiro | ✅ | alerj, doe, sefaz, tjrj | [RJ.md](ufs/RJ.md) | MVP |
| RN | Rio Grande do Norte | 🟡 | sapl-proposicoes | — | |
| RS | Rio Grande do Sul | ✅ | alrs, doe, sefaz | [RS.md](ufs/RS.md) | MVP |
| RO | Rondônia | 🟡 | sapl-proposicoes | — | |
| RR | Roraima | 🟡 | sapl-proposicoes | — | Re-verificação trimestral |
| SC | Santa Catarina | 🟡 | sapl-proposicoes, tjsc | — | Re-verificação trimestral |
| SP | São Paulo | ✅ | alesp, doe, sefaz, tit-sp, tjsp | [SP.md](ufs/SP.md) | MVP |
| SE | Sergipe | 🟡 | sapl-proposicoes | — | |
| TO | Tocantins | 🟡 | portal | — | Re-verificação trimestral |

**Resumo**: 5 ✅ ativas, 22 🟡 prontas, 0 ❌ sem fonte.

## Federais (não-UF)

| Fonte | Cobertura |
|---|---|
| LexML | Atos normativos federais consolidados |
| LexML Jurisprudência | Acórdãos federais |
| STF | RSS oficial |
| STJ | RSS oficial |
| TRFs 1-6 | RSS por região |
| CNJ | Provimentos cartorários |
| Câmara dos Deputados | Proposições legislativas |
| Senado Federal | Atividade legislativa |
| Confaz | Convênios ICMS/ITCD |
| Receita Federal | Atos da RFB |
| PGFN | Pareceres |
| AGU | Pareceres jurídicos |
| Conjur, Migalhas, JOTA, IBDFAM | Doutrina e notícias |
| Estadão, Folha SP, Valor Econômico | Cobertura jornalística |
| BDTD CAPES, Google Scholar, SciELO | Doutrina acadêmica |

## Como ativar uma UF nova

1. Verificar os critérios de ativação em `regras/40-regras-negocio.md`:
   - YAML existe em `sources/{UF}/` para ≥ 2 fontes.
   - Cassette VCR em `tests/integration/test_sources_{UF}.py` passa.
   - 1 item real classificado em sandbox.
   - `docs/ufs/{UF}.md` criado.
2. `/estados ativar BA` no bot Telegram.
3. Próxima execução do cron já coleta.
