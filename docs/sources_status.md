# Status das fontes (auditoria 2026-04-25)

Audit batch via `curl --max-time 15` mais teste via proxy_br quando aplicável.

## ✅ Funcionando em produção

| Fonte | UF | Parser | Como roda |
|---|---|---|---|
| LexML | _federal | `lexml` | API SRU oficial, federal |
| JOTA principal | _federal | `generic_rss` | RSS válido |
| STF notícias | _federal | `generic_rss` | RSS válido |
| STJ notícias | _federal | `generic_rss` | RSS válido |
| ALMG proposições | MG | `almg` | API JSON, via proxy_br |
| ALMG legislação | MG | `almg` | API JSON, via proxy_br |

**Total**: 6 fontes (4 federais + 2 estaduais MG).

## ⛔ Inativas — RSS depreciado, requer migração para HTML scraping

| Fonte | UF | Status atual | Próximo passo |
|---|---|---|---|
| TJSP notícias | SP | RSS 301→HTML | Migrar para `generic_html` |
| TJRJ notícias | RJ | RSS 404 | URL morta; investigar feed novo ou HTML |
| TRF1 | _federal | 504/timeout | RSS desativado; investigar |
| TRF2 | _federal | RSS 302→HTML | Migrar para `generic_html` |
| TRF3 | _federal | timeout | Possível geo-restrito; testar via proxy |
| TRF4 | _federal | RSS 302→HTML | Migrar para `generic_html` |
| TRF5 | _federal | 404 | URL morta |
| TRF6 | _federal | timeout | Possível geo-restrito |
| CNJ | _federal | timeout direto E via proxy | Site fora do ar; aguardar voltar |
| IBDFAM | _federal | sem RSS público | Documentado: não-implementável atualmente |

## ⛔ Inativas — Sites estaduais (puro HTML, sem API JSON conhecida)

Status `200/302` indica que site responde mas é HTML. Ativação requer
implementação de `generic_html` collectors com seletores CSS específicos
de cada portal — atualmente **fora do escopo** (decisão do dono).

| Fonte | UF | URL | Tipo |
|---|---|---|---|
| ALESP proposições | SP | al.sp.gov.br | HTML; portal de dados-abertos retorna XML mas endpoints específicos retornam 404 |
| Imprensa Oficial SP | SP | imprensaoficial.com.br | ASP.NET com VIEWSTATE |
| SEFAZ-SP | SP | portal.fazenda.sp.gov.br | HTML |
| ALERJ proposições | RJ | alerj.rj.gov.br | HTML |
| IOERJ DOE | RJ | ioerj.com.br | HTML |
| SEFAZ-RJ | RJ | fazenda.rj.gov.br | HTML |
| AL/RS proposições | RS | al.rs.gov.br | HTML |
| DOE-RS | RS | doe.rs.gov.br | TIMEOUT — possível geo-restrito |
| SEFAZ-RS | RS | fazenda.rs.gov.br | TIMEOUT — possível geo-restrito |
| CL-DF | DF | cl.df.gov.br | URL atual retorna 404; localizar correta |
| DODF | DF | dodf.df.gov.br | HTML |
| SEFAZ-DF | DF | fazenda.df.gov.br | URL atual retorna 404 |

## 🎯 Próximos passos sugeridos por valor

### Alto valor / curto prazo (1-2 dias cada)

1. **Implementar `generic_html` para ALESP** — única ALE de SP com volume legislativo
   significativo. Pesquisa de proposições aceita query params, dá pra parsear
   resultado HTML estruturado.
2. **Implementar `generic_html` para SEFAZ-SP legislação ITCMD** — alíquota
   progressiva proposta há anos, mudanças importantes.
3. **Atualizar URLs mortas** (CL-DF, SEFAZ-DF, TRF5, TJRJ) — descobrir URL atual
   por busca manual e atualizar YAML.

### Médio valor / médio prazo (3-5 dias cada)

4. Implementar **collectors custom para ALERJ, AL-RS** (mesmo padrão ALMG se
   tiverem APIs JSON; senão via HTML).
5. **TRFs 1/3/6** via proxy_br (testar se geo-restrição é o bloqueio).
6. **TJSP, TJRJ, TJMG** notícias via HTML scraping.

### Baixo valor / fase futura

7. ALEs/SEFAZs/DOEs estaduais restantes.
8. CNJ aguardar volta (se não voltar em 30d, marcar como permanente-fora).

## Decisão do dono pendente

A maior parte das fontes estaduais depende de **HTML scraping**, que
atualmente está fora do MVP. Para destravar SP/RJ/RS/DF efetivamente,
precisamos:
- (A) Habilitar `generic_html` collectors e implementar por UF, ou
- (B) Continuar focado em federais + ALMG, expandir lentamente.
