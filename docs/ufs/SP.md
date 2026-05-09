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
- `alesp.yaml` — proposituras (PLs, PECs, etc.). **ATIVA desde 2026-05-09** — parser custom `alesp` consumindo `/repositorioDados/processo_legislativo/proposituras.zip` (dados abertos oficiais; streaming-parse com defusedxml).
- `sefaz.yaml` — atos normativos da SEFAZ. **ATIVA desde 2026-05-09** — parser custom `sefaz_sp` via API SharePoint REST (`legislacao.fazenda.sp.gov.br/_api/Web/Lists`).
- `tjsp.yaml` — Tribunal de Justiça (notícias). **ATIVA desde 2026-05-08** — `parser: generic_html` apontando para `/Noticias`.
- `doe.yaml` — Diário Oficial do Estado. **Inativa por design** (redundante com SEFAZ-SP, que já cobre os atos publicados via API).
- `tit-sp.yaml` — Tribunal de Impostos e Taxas. **Inativa** (decisões em ePAT sem API pública).

## Status atual
3 das 5 fontes ativas: ALESP (proposituras), SEFAZ-SP (atos administrativos),
TJSP (jurisprudência). Cobertura legislativa adicional via `lexml-portal`
federal (ativo), que indexa atos estaduais por URN.

**Histórico**:
- 2026-04-25 (MVP): todas as 5 fontes criadas como stubs (`ativo: false`).
- 2026-05-08: TJSP reativado (`generic_html` em `/Noticias`).
- 2026-05-09: SEFAZ-SP e ALESP ativadas via collectors custom:
  - **SEFAZ-SP** descobre que SharePoint expõe API REST nativa em `_api/web/lists`,
    retornando JSON estruturado sem precisar renderizar JavaScript.
    Smoke test 2026-05-08: 7 itens ITCMD detectados nos últimos 100 modificados.
  - **ALESP** usa o ZIP diário de dados abertos com ~270 mil proposituras,
    streaming-parse para baixo overhead de memória.
    Smoke test 2026-05-08: 4 PLs nos últimos 60 dias com keywords ITCMD/sucessão.

**DOE-SP e TIT-SP permanecem inativas por escolha técnica**:
- DOE-SP é redundante com SEFAZ-SP, sem API pública, e exigiria parsing
  POST de ASP.NET (frágil).
- TIT-SP não tem API pública de jurisprudência; decisões ficam em ePAT
  protegido por login do contribuinte.

## Referências externas
- ALESP: https://www.al.sp.gov.br/
- SEFAZ-SP: https://portal.fazenda.sp.gov.br/
- Imprensa Oficial: https://www.imprensaoficial.com.br/
- TJSP: https://www.tjsp.jus.br/
