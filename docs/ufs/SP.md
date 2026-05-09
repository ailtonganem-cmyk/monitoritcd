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
- `alesp.yaml` — projetos de lei. **Inativa** (ASP.NET com VIEWSTATE; precisa parser custom).
- `sefaz.yaml` — atos normativos da SEFAZ. **Inativa** (SharePoint com renderização JS; lento, parsing HTML estático não traz conteúdo).
- `doe.yaml` — Diário Oficial do Estado. **Inativa** (Imprensa Oficial usa POST/VIEWSTATE).
- `tit-sp.yaml` — Tribunal de Impostos e Taxas. **Inativa** (URL antiga retorna timeout/redirect).
- `tjsp.yaml` — Tribunal de Justiça (notícias). **ATIVA desde 2026-05-08** — `parser: generic_html` apontando para `/Noticias`.

## Status atual
Apenas `tjsp.yaml` está ativa. Cobertura legislativa de SP vem ainda do
`lexml-portal` federal (ativo), que indexa atos estaduais via URN
`urn:lex:br;sp:estadual:...`.

**Histórico**:
- 2026-04-25 (MVP): todas as 5 fontes criadas como stubs (`ativo: false`,
  selectors não validados).
- 2026-05-08: TJSP reativado com `parser: generic_html`, URL `/Noticias`,
  selectors validados ao vivo (10 itens/página, layout `<div.col-sm-9><a.noticia-description><h1>`).

**Para ativar as demais (alesp, sefaz, doe, tit)**:
1. Resolver questões técnicas listadas (ASP.NET POST, SharePoint JS, etc.).
2. Validar URL e parser via `--dry-run` ou cassette VCR.
3. Confirmar coleta retorna ≥ 1 item ITCMD em sandbox.
4. Trocar `ativo: false` → `true` no YAML (PR + CI verde).
5. SP já está em `active_uf` no Firestore (confirmado 2026-05-08), então
   YAML reativado entra em coleta na próxima execução do cron.

## Referências externas
- ALESP: https://www.al.sp.gov.br/
- SEFAZ-SP: https://portal.fazenda.sp.gov.br/
- Imprensa Oficial: https://www.imprensaoficial.com.br/
- TJSP: https://www.tjsp.jus.br/
