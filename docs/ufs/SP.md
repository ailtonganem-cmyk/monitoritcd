# SP — São Paulo

## Tributo
- **Nomenclatura**: ITCMD
- **Lei principal**: Lei 10.705/2000
- **Alíquota**: 4% **fixa** (não progressiva)
- **Discussões ativas**: PLs propondo alíquota progressiva (acompanhar)

## Particularidades
- Maior arrecadação de ITCMD do Brasil.
- Holding familiar é tema de constante litígio (autuação por dissimulação).
- Súmula vinculante de TJSP/STJ frequente.
- "Valor venal de referência" — base de cálculo definida pela SEFAZ-SP.

## Fontes mapeadas
- `alesp.yaml` — projetos de lei.
- `sefaz.yaml` — atos normativos da SEFAZ.
- `doe.yaml` — Diário Oficial do Estado.
- `tjsp.yaml` — Tribunal de Justiça (notícias e jurisprudência).

## Status
Todas as fontes mapeadas em `sources/SP/` mas com `ativo: false` e `fragile: true`.
**Antes de ativar:**
1. Validar URL do feed/página.
2. Validar selectors CSS (rodar coletor com `--dry-run`).
3. Confirmar que coleta retorna ≥ 1 item ITCMD em ambiente de teste.
4. Ativar via bot: `/estados ativar SP`.

## Referências externas
- ALESP: https://www.al.sp.gov.br/
- SEFAZ-SP: https://portal.fazenda.sp.gov.br/
- Imprensa Oficial: https://www.imprensaoficial.com.br/
- TJSP: https://www.tjsp.jus.br/
