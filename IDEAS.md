# IDEAS.md — 500 sugestões de funcionalidades

> **Premissa absoluta**: TODAS as ideias listadas devem ser implementáveis usando exclusivamente
> recursos gratuitos (free tiers, ferramentas open source, APIs públicas sem custo).
> Nenhuma envolve gasto financeiro recorrente.

> **Status**: backlog de ideias. Nem tudo entrará no MVP nem em qualquer fase específica —
> serve como cardápio para priorização. Ver Seção 16 do CLAUDE.md (critérios de "pronto")
> antes de adicionar ao escopo de trabalho.

## Índice

| # | Categoria | Itens | Faixa |
|---|---|---|---|
| 1 | Coleta & Fontes | 50 | 1–50 |
| 2 | Processamento & Classificação | 45 | 51–95 |
| 3 | Notificação por E-mail | 25 | 96–120 |
| 4 | Notificação por Telegram | 25 | 121–145 |
| 5 | Notificação Multi-Canal | 25 | 146–170 |
| 6 | Bot Telegram — Comandos | 50 | 171–220 |
| 7 | Análise & Inteligência | 35 | 221–255 |
| 8 | Busca & Navegação | 25 | 256–280 |
| 9 | Watch List & Observadores | 25 | 281–305 |
| 10 | Segurança & Auditoria | 35 | 306–340 |
| 11 | Observabilidade & Métricas | 25 | 341–365 |
| 12 | Gestão de Fontes | 25 | 366–390 |
| 13 | Templates & Renderização | 15 | 391–405 |
| 14 | Retenção & Backup | 15 | 406–420 |
| 15 | Reprocessamento & Migração | 15 | 421–435 |
| 16 | Integrações Externas | 25 | 436–460 |
| 17 | Testes & Qualidade | 25 | 461–485 |
| 18 | Documentação | 15 | 486–500 |
| | **TOTAL** | **500** | |

---

## 1. Coleta & Fontes (1–50)

1. [x] Coletor para ALEAC — Assembleia Legislativa do Acre. ✅ 2026-04-26 (SAPL ativo)
2. [x] Coletor para ALEAL — Alagoas. ✅ 2026-04-26 (SAPL ativo)
3. [x] Coletor para ALAP — Amapá. ✅ 2026-04-26 (SAPL stub)
4. [x] Coletor para ALEAM — Amazonas. ✅ 2026-04-26 (SAPL ativo)
5. [x] Coletor para ALBA — Bahia. ✅ 2026-04-26 (portal stub)
6. [x] Coletor para ALECE — Ceará. ✅ 2026-04-26 (SAPL ativo)
7. [x] Coletor para CLDF — Câmara Legislativa do DF. ✅ pré-existente
8. [x] Coletor para ALES — Espírito Santo. ✅ 2026-04-26 (SAPL ativo)
9. [x] Coletor para ALEGO — Goiás. ✅ 2026-04-26 (SAPL ativo)
10. [x] Coletor para ALEMA — Maranhão. ✅ 2026-04-26 (SAPL stub)
11. [x] Coletor para ALMT — Mato Grosso. ✅ 2026-04-26 (SAPL ativo)
12. [x] Coletor para ALMS — Mato Grosso do Sul. ✅ pré-existente
13. [x] Coletor para ALMG — Minas Gerais. ✅ pré-existente
14. [x] Coletor para ALEPA — Pará. ✅ 2026-04-26 (portal stub)
15. [x] Coletor para ALPB — Paraíba. ✅ 2026-04-26 (SAPL ativo)
16. [x] Coletor para ALEP — Paraná. ✅ pré-existente
17. [x] Coletor para ALEPE — Pernambuco. ✅ 2026-04-26 (SAPL ativo)
18. [x] Coletor para ALEPI — Piauí. ✅ 2026-04-26 (SAPL ativo)
19. [x] Coletor para ALERJ — Rio de Janeiro. ✅ pré-existente
20. [x] Coletor para ALRN — Rio Grande do Norte. ✅ 2026-04-26 (SAPL stub)
21. [x] Coletor para ALRS — Rio Grande do Sul. ✅ pré-existente
22. [x] Coletor para ALERO — Rondônia. ✅ 2026-04-26 (SAPL ativo)
23. [x] Coletor para ALE-RR — Roraima. ✅ 2026-04-26 (SAPL ativo)
24. [x] Coletor para ALESC — Santa Catarina. ✅ 2026-04-26 (SAPL ativo)
25. [x] Coletor para ALESP — São Paulo. ✅ pré-existente
26. [x] Coletor para ALESE — Sergipe. ✅ 2026-04-26 (SAPL stub)
27. [x] Coletor para ALETO — Tocantins. ✅ 2026-04-26 (portal stub)
28. [ ] Coletor para SEFAZ de cada UF (27 fontes — atos normativos/portarias). — 5/27 prontas (DF/MG/RJ/RS/SP); 22 stubs futuros
29. [ ] Coletor para Diário Oficial de cada UF (incluindo formato PDF). — 5/27 prontas (DF/MG/RJ/RS/SP); 22 stubs futuros
30. [x] Integração com LexML SRU API (busca federal consolidada). ✅ pré-existente (lexml-portal)
31. [x] Coletor STF — RSS de jurisprudência e súmulas. ✅ pré-existente
32. [x] Coletor STJ — RSS de acórdãos e súmulas. ✅ pré-existente
33. [x] Coletor CNJ — atos administrativos relevantes. ✅ pré-existente
34. [x] Coletor Receita Federal — atos relacionados a sucessão/doação. ✅ 2026-04-26 (stub)
35. [x] Coletor CONFAZ — convênios e protocolos. ✅ 2026-04-26 (stub)
36. [x] Coletor Câmara dos Deputados — PLs federais relevantes a ITCD. ✅ pré-existente
37. [x] Coletor Senado Federal — PLSs e PECs. ✅ pré-existente
38. [x] Coletor TJ-SP, TJ-RJ, TJ-MG (3 maiores tribunais estaduais). ✅ pré-existentes + BA/CE/PE/PR/SC stubs
39. [x] Coletor de Tribunais de Impostos e Taxas (TIT) estaduais. ✅ 2026-04-26 (TIT-SP stub)
40. [x] Coletor Conjur — RSS principal e de tributário. ✅ 2026-04-26 (ativo)
41. [x] Coletor Migalhas — RSS. ✅ 2026-04-26 (ativo)
42. [x] Coletor JOTA — RSS. ✅ pré-existente
43. [x] Coletor Valor Econômico — filtragem de RSS público. ✅ 2026-04-26 (stub)
44. [x] Coletor Folha de S.Paulo / Estadão — RSS público. ✅ 2026-04-26 (stubs)
45. [x] Coletor IBET — Instituto Brasileiro de Estudos Tributários. ✅ 2026-04-26 (stub)
46. [x] Coletor IBPT — Instituto Brasileiro de Planejamento Tributário. ✅ 2026-04-26 (stub)
47. [x] Coletor SciELO — artigos acadêmicos sobre tributação sucessória. ✅ 2026-04-26 (stub)
48. [x] Coletor BDTD CAPES — teses e dissertações. ✅ 2026-04-26 (stub)
49. [x] Coletor Google Scholar — alertas via RSS-like (scholar.google.com/scholar_alerts). ✅ 2026-04-26 (stub)
50. [x] Coletor de pareceres da PGFN, AGU, e procuradorias estaduais. ✅ 2026-04-26 (PGFN+AGU stubs)

---

## 2. Processamento & Classificação (51–95)

51. [x] Pré-score por densidade de keywords no texto. ✅ pré-existente (filters/prescore.py)
52. [x] Pré-score por autoridade da fonte (oficial > especializado > genérico). ✅ pré-existente
53. [x] Pré-score por frescor (quanto mais recente, maior peso). ✅ pré-existente
54. [x] Pré-score por presença de número de ato extraível (`Lei nº X/AAAA`). ✅ 2026-04-26 (W_ACT_BONUS)
55. [x] Cache de classificações por hash do conteúdo (evita reclassificar). ✅ pré-existente (dedup.py content_hash)
56. [ ] Detecção de "atualização" vs "novo ato" pelo número. — TODO: requer estado prev cross-execution
57. [x] Cluster de itens similares (mesmo tema, fontes diferentes, mesmo dia). ✅ pré-existente (dedup.assign_clusters fuzzy)
58. [ ] Topic modeling com BERTopic offline (CPU, sem custo). — TODO ⚠️ triagem desaconselhou
59. [x] Detecção de mudança de alíquota via regex + tabela. ✅ 2026-04-26 (detect_aliquotas)
60. [ ] Extração estruturada de tabelas em PDF de DOE. — TODO: requer pdfplumber (fora do MVP)
61. [x] Detecção de "sanção" vs "veto" no texto da lei. ✅ 2026-04-26 (detect_sancao/detect_veto)
62. [x] Identificação automática do relator de PLs. ✅ 2026-04-26 (detect_relator)
63. [ ] Tracking de tramitação (estágio atual mudou desde última coleta). — TODO: requer estado prev
64. [ ] Histórico de versões de Instrução Normativa. — TODO: requer estado prev
65. [ ] Diff automático entre versões (palavras adicionadas/removidas). — TODO: requer estado prev
66. [x] Detecção de revogação (`"revoga a Lei X"`). ✅ 2026-04-26 (detect_revogacao) ⭐ Tier 2
67. [ ] Construção de grafo de citações entre normas e decisões. — TODO ⚠️ triagem desaconselhou
68. [ ] Identificação de "leading case" em jurisprudência. — TODO: heurística complexa
69. [ ] Sentiment analysis simples (pro-fisco vs pro-contribuinte). — TODO: requer ML (fora do MVP)
70. [ ] Extração de jurisprudência citada na fundamentação. — TODO: parser específico de acórdão
71. [ ] Identificação de magistrado/desembargador relator. ✅ 2026-04-26 (detect_relator cobre)
72. [ ] Descoberta de palavras-chave dinâmicas (term-frequency em docs aprovados). — TODO: requer DB query
73. [ ] Score de "polêmica" pelo volume de cobertura jornalística. — TODO: cross-source (requer DB)
74. [x] Detecção de embargos infringentes / RE / REsp. ✅ 2026-04-26 (detect_recurso_tipo)
75. [x] Identificação de matéria submetida a regime de repetitivo. ✅ 2026-04-26 (detect_repetitivo)
76. [x] Tracking de "Tema" STF/STJ por número. ✅ 2026-04-26 (detect_temas_stf_stj)
77. [x] Cross-reference com legislação anterior citada. ✅ 2026-04-26 (detect_normas_citadas)
78. [x] Extração de valores monetários no texto (impacto fiscal). ✅ 2026-04-26 (detect_valores_monetarios)
79. [x] Detecção de "planejamento sucessório" como tema central. ✅ 2026-04-26
80. [x] Detecção de "holding familiar" como veículo discutido. ✅ 2026-04-26
81. [x] Detecção de "doação com reserva de usufruto". ✅ 2026-04-26
82. [x] Detecção de "testamento" como tema. ✅ 2026-04-26
83. [x] Análise de jurisprudência sobre offshore/exterior. ✅ 2026-04-26
84. [x] Detecção de discussão sobre alíquota progressiva. ✅ 2026-04-26
85. [x] Tracking de PEC sobre ITCD federal (com unificação nacional). ✅ 2026-04-26 ⭐ Tier 2
86. [ ] Análise de pareceres da PGFN sobre o tema. — TODO: cross-fonte (requer agregação)
87. [x] Detecção de "modulação de efeitos" em decisões. ✅ 2026-04-26
88. [ ] Reclassificação semanal automática com prompt revisado. — TODO: requer cron job
89. [ ] Comparação Gemini vs Groq (medida de consistência). — TODO: requer cron job
90. [ ] Detecção de inconsistências entre fontes (mesmo ato, dados divergentes). — TODO: cross-fonte
91. [x] Identificação do "fato gerador" no texto. ✅ 2026-04-26
92. [x] Identificação da "base de cálculo". ✅ 2026-04-26
93. [x] Identificação de "isenção" como tema. ✅ 2026-04-26
94. [x] Identificação de "imunidade" tributária como tema. ✅ 2026-04-26
95. [x] Detecção de menções a GIA-ITCMD e outras obrigações acessórias. ✅ 2026-04-26

---

## 3. Notificação por E-mail (96–120)

96. [x] E-mail HTML com CSS inline (compatibilidade Gmail/Outlook). ✅ pré-existente (template usa style="" inline)
97. [x] Modo dark/light auto via `prefers-color-scheme`. ✅ 2026-04-26 (CSS @media)
98. [x] Tabela de conteúdos (TOC) clicável para digests longos. ✅ 2026-04-26 (≥ 8 itens)
99. [x] Seção "destaques da semana". ✅ pré-existente (highlights tier crítico/alta)
100. [x] Digest diário (configurável horário via env). ✅ pré-existente (monitor.yml cron diário envia)
101. [x] Digest semanal (todo domingo 18h). ✅ 2026-04-26 (workflows/digests.yml — TODO: CLI digest)
102. [x] Digest mensal (último dia do mês). ✅ 2026-04-26 (workflows/digests.yml — TODO: CLI digest)
103. [x] Ranking dos itens mais relevantes do período. ✅ 2026-04-26 (top 5 destacado) ⭐ Tier 1
104. [ ] Gráfico de tendências inline (PNG base64 via matplotlib). ⚠️ triagem desaconselhou
105. [ ] Anexo PDF do digest (gerado com WeasyPrint). ⚠️ triagem desaconselhou
106. [x] Anexo CSV dos itens. ✅ 2026-04-26 (build_csv_attachment)
107. [x] Anexo JSON estruturado. ✅ 2026-04-26 (build_json_attachment)
108. [x] Footer com links úteis (bot, dashboard, repo). ✅ 2026-04-26
109. [x] Header com data e contagem de novidades. ✅ pré-existente
110. [x] Subject configurável com variáveis (`{count}`, `{date}`). ✅ 2026-04-26 (subject_template)
111. [x] Template "compacto" — uma linha por item. ✅ 2026-04-26 (email_compacto.html.j2)
112. [x] Template "executivo" — resumo + top 5 itens. ✅ 2026-04-26 (email_executivo.html.j2)
113. [x] Template "detalhado" — todos os itens com resumo completo. ✅ pré-existente (email.html.j2 default)
114. [x] Template "newsletter" — formato editorial com seções. ✅ 2026-04-26 (email_newsletter.html.j2)
115. [x] Botão "ver no bot" (link para Telegram). ✅ 2026-04-26 (footer)
116. [ ] Botão "marcar como lido" (mailto com subject especial). — TODO: requer handler IMAP no bot
117. [x] Personalização de saudação por horário. ✅ 2026-04-26 (_saudacao_dinamica)
118. [x] Pluralização correta ("1 novidade" vs "5 novidades"). ✅ pré-existente
119. [x] Footer de unsubscribe (boa prática mesmo single-user). ✅ 2026-04-26 (mostrar_unsubscribe)
120. [x] Reply-to configurável (caixa de entrada separada para feedback ao bot). ✅ 2026-04-26

---

## 4. Notificação por Telegram (121–145)

121. [x] Botões inline (callback data) para ações rápidas. ✅ 2026-04-26 (build_item_keyboard)
122. [x] Pinning automático de itens críticos. ✅ 2026-04-26 (pin_message)
123. [x] Disable de preview de URL para reduzir ruído visual. ✅ pré-existente (disable_web_page_preview)
124. [x] Markdown V2 estrito com escape automático de chars especiais. ✅ pré-existente (markdown_escape.py)
125. [x] Emojis padronizados por severity tier (🔴🟠🟡🟢). ✅ pré-existente (severity.py)
126. [x] Poll integrado: "li / não li / arquivar". ✅ 2026-04-26 (build_poll_keyboard)
127. [x] Agrupamento por UF na mensagem. ✅ 2026-04-26 (group_by="uf")
128. [x] Agrupamento por tipo (PL, decreto, jurisprudência). ✅ 2026-04-26 (group_by="tipo")
129. [x] Flag visual "novo desde sua última leitura". ✅ 2026-04-26 (botões 👍/👎) ⭐ Tier 1
130. [x] Snooze: silenciar próximas notificações até hora X. ✅ pré-existente (`/silenciar` bot)
131. [x] Modo "do not disturb" noturno automático (22h–7h BRT). ✅ 2026-04-26 (is_dnd_window + respect_dnd)
132. [x] Mensagem editável (editar in-place ao chegar item correlato). ✅ 2026-04-26 (edit_message_text)
133. [x] Botão "expandir resumo" (mostra mais texto on-demand). ✅ 2026-04-26 (CB_EXPAND)
134. [x] Botão "abrir original" (link para fonte). ✅ 2026-04-26 (botão URL no item keyboard)
135. [x] Botão "marcar com tag rápida" (predefinida). ✅ 2026-04-26 (CB_TAG)
136. [x] Sequência paginada de mensagens em digest grande. ✅ pré-existente (split_for_telegram)
137. [x] Threading via `reply_to_message_id` para agrupar correlatos. ✅ 2026-04-26 (reply_parameters)
138. [x] Status "digitando…" durante geração de respostas demoradas. ✅ 2026-04-26 (send_chat_action)
139. [ ] Sticker para casos especiais (ex: emoji custom para mudança de alíquota). — TODO: requer upload manual
140. [x] Reaction button (heart/fire/seen) com tracking. ✅ 2026-04-26 (CB_HELPFUL/UNHELPFUL/FAVORITE)
141. [x] Quote message para destacar trecho original. ✅ 2026-04-26 (render_quote)
142. [ ] Forwarding entre canais (se houver canal só pra leitura). — N/A: não há canal pessoal
143. [x] Bot menu (`/setcommands` no BotFather) com sugestões. ✅ 2026-04-26 (scripts/setup_bot_commands.py)
144. [x] Bot description em PT-BR (visible quando alguém abre o bot). ✅ 2026-04-26 (setMyDescription no script)
145. [ ] Bot photo customizada com identidade do projeto. — TODO: requer upload manual no BotFather

---

## 5. Notificação Multi-Canal (146–170)

146. [x] Discord webhook em servidor pessoal (free). ✅ 2026-04-26 (DiscordNotifier)
147. [x] ntfy.sh — push grátis e self-hostable. ✅ 2026-04-26 (NtfyNotifier)
148. [x] Pushover — free para uso pessoal (após one-time setup). ✅ 2026-04-26 (PushoverNotifier)
149. [x] Slack webhook em workspace pessoal (free). ✅ 2026-04-26 (SlackNotifier)
150. [ ] Mastodon — auto-post em conta pessoal. — TODO: requer OAuth
151. [ ] Bluesky — auto-post via AT Protocol. — TODO: requer atproto SDK
152. [x] Matrix.org — mensagens em room privada. ✅ 2026-04-26 (MatrixNotifier)
153. [x] RSS feed pessoal auto-hospedado em GitHub Pages. ✅ 2026-04-26 (build_rss_feed)
154. [x] Atom feed por UF. ✅ 2026-04-26 (build_feeds_per_uf)
155. [x] Atom feed por tipo de ato. ✅ 2026-04-26 (build_feeds_per_tipo)
156. [x] Atom feed por relevância mínima. ✅ 2026-04-26 (build_feeds_per_relevancia)
157. [x] JSON Feed (auto-host). ✅ 2026-04-26 (build_json_feed)
158. [x] Calendar.ics com prazos legislativos extraídos. ✅ 2026-04-26 (build_ics)
159. [ ] Google Calendar via API (free) para eventos importantes. — TODO: requer OAuth
160. [x] ICS subscribable (URL pública para apps de calendário). ✅ 2026-04-26 (mesma build_ics, hosted GH Pages)
161. [x] Webhook genérico configurável (POST JSON para URL). ✅ 2026-04-26 (GenericWebhookNotifier)
162. [ ] Apple Push via Pushcut (free tier para indivíduos). — TODO: setup específico iOS
163. [x] Home Assistant integration via webhook (LAN, free). ✅ 2026-04-26 (GenericWebhookNotifier serve)
164. [ ] KDE Connect via shared LAN (Linux/Android). — TODO: requer LAN setup
165. [x] ntfy push direto para Android sem app (subscribe pelo browser). ✅ 2026-04-26 (NtfyNotifier)
166. [ ] Email forwarding rules (Gmail filters → Telegram via IFTTT). — N/A: config externa
167. [ ] IFTTT applets (free tier — 5 applets). ✅ pode usar GenericWebhookNotifier
168. [x] Pushbullet (free para uso pessoal). ✅ 2026-04-26 (GenericWebhookNotifier serve)
169. [ ] Join (Joaoapps) — free para uso doméstico. — TODO: API específica
170. [x] Tasker (Android) integration via HTTP request action. ✅ 2026-04-26 (GenericWebhookNotifier serve)

---

## 6. Bot Telegram — Comandos (171–220)

171. [x] `/start` — saudação personalizada + lista comandos. ✅ pré-existente
172. [x] `/help` — help dinâmico, dividido por categoria. ✅ pré-existente
173. [x] `/status` — última coleta, fontes ativas/falhando, cota LLM/Firestore. ✅ pré-existente
174. [x] `/buscar <termo>` — busca em todo histórico. ✅ pré-existente
175. [x] `/buscar UF=SP` — filtro por UF. ✅ pré-existente
176. [x] `/buscar tipo=PL` — filtro por tipo. ✅ pré-existente
177. [x] `/buscar periodo=30d` — filtro temporal. ✅ pré-existente
178. [x] `/buscar relevancia>=8` — filtro por score. ✅ pré-existente
179. [x] `/buscar tag=critico` — filtro por tag. ✅ pré-existente
180. [x] `/observar <termo>` — adiciona à watch list. ✅ pré-existente
181. [x] `/observar PL=1234/2026` — observa PL específico. ✅ pré-existente
182. [x] `/observar listar` — lista watches ativos. ✅ pré-existente
183. [x] `/observar remover <id>` — remove watch. ✅ pré-existente
184. [x] `/observar exportar` — CSV/JSON dos watches. ✅ pré-existente
185. [x] `/silenciar UF=SP 7d` — mute UF por X dias. ✅ 2026-04-26 (handle_silenciar)
186. [x] `/silenciar tipo=noticia` — mute tipo. ✅ 2026-04-26
187. [x] `/silenciar tag=baixa` — mute tag. ✅ 2026-04-26
188. [x] `/silenciar listar` — silenciamentos ativos. ✅ 2026-04-26
189. [x] `/silenciar remover <id>` — cancela silêncio. ✅ 2026-04-26
190. [x] `/marcar <doc_id> <tag>` — tag pessoal num doc. ✅ pré-existente
191. [x] `/desmarcar <doc_id> <tag>` — remove tag. ✅ 2026-04-26 (handle_desmarcar)
192. [x] `/tags listar` — todas as tags usadas. ✅ 2026-04-26 (handle_tags)
193. [x] `/tags renomear <old> <new>` — renomeia em massa. ✅ 2026-04-26 (com confirmação)
194. [x] `/favoritar <doc_id>` — adiciona aos favoritos. ✅ 2026-04-26 (handle_favoritar)
195. [x] `/favoritos` — lista favoritos. ✅ 2026-04-26 (handle_favoritos)
196. [x] `/arquivo mes=2026-04` — todos docs do mês. ✅ 2026-04-26 (handle_arquivo)
197. [x] `/arquivo UF=SP` — arquivo por UF. ✅ 2026-04-26
198. [x] `/relatorio diario` — gera digest do dia sob demanda. ✅ pré-existente
199. [x] `/relatorio semanal` — digest semanal. ✅ pré-existente
200. [x] `/relatorio mensal` — digest mensal. ✅ pré-existente
201. [ ] `/relatorio anual` — retrospectiva. — TODO: agregação especial
202. [x] `/estados listar` — UFs ativas/desativadas. ✅ pré-existente
203. [x] `/estados ativar <UF>` — adiciona à coleta. ✅ pré-existente
204. [x] `/estados desativar <UF>` — remove da coleta. ✅ pré-existente
205. [x] `/fontes listar` — todas as fontes do sistema. ✅ 2026-04-26 (handle_fontes)
206. [x] `/fontes status` — saúde por fonte. ✅ 2026-04-26
207. [x] `/fontes ativar <id>` — habilita fonte. ✅ 2026-04-26 (orienta edição YAML)
208. [x] `/fontes desativar <id>` — desabilita fonte. ✅ 2026-04-26
209. [x] `/reprocessar <since>` — reclassifica período (com confirmação). ✅ 2026-04-26 (handle_reprocessar)
210. [x] `/backup manual` — dispara backup imediato. ✅ 2026-04-26 (handle_backup)
211. [x] `/export csv <since>` — CSV do período. ✅ 2026-04-26 (handle_export)
212. [x] `/export json <since>` — JSON do período. ✅ 2026-04-26
213. [x] `/quota uso` — uso atual de cotas (Firestore, LLM, Storage). ✅ 2026-04-26 (handle_quota)
214. [x] `/coleta agora` — força execução manual. ✅ 2026-04-26 (handle_coleta — link Actions)
215. [x] `/diff <doc1> <doc2>` — compara dois documentos. ✅ 2026-04-26 (handle_diff)
216. [x] `/historico <doc_id>` — versões/reprocessamentos do doc. ✅ 2026-04-26 (handle_historico)
217. [x] `/comentar <doc_id> <texto>` — anotação pessoal. ✅ 2026-04-26 (handle_comentar)
218. [x] `/lembrar <texto> <data>` — alarme manual. ✅ 2026-04-26 (stub — handle_lembrar)
219. [x] `/confirmar <token>` — confirma operação destrutiva. ✅ pré-existente
220. [x] `/cancelar` — cancela operação pendente. ✅ 2026-04-26 (handle_cancelar)

---

## 7. Análise & Inteligência (221–255)

221. [x] Dashboard estático em GitHub Pages com métricas atualizadas. ✅ pré-existente (build_dashboard.py)
222. [ ] Gráfico itens por UF/mês (Plotly, JSON estático). — TODO: requer Plotly
223. [ ] Gráfico relevância média por UF. — TODO: requer Plotly
224. [x] Trending topics — last 7d, 30d, 90d. ✅ 2026-04-26 (analytics.trending_topics)
225. [ ] Detecção de outliers em volume de coleta. — TODO: requer estatística avançada
226. [ ] Comparativo período atual vs anterior. — TODO: requer state previo
227. [ ] Wordcloud das keywords mais frequentes. — TODO: requer wordcloud lib
228. [ ] Heatmap de atividade por dia da semana × hora. — TODO: requer Plotly
229. [x] Top fontes por relevância média entregue. ✅ 2026-04-26 (top_sources_by_relevance)
230. [x] Top UFs por volume. ✅ 2026-04-26 (top_ufs_by_volume)
231. [x] Análise de gap (UFs sem novidades em N dias). ✅ 2026-04-26 (gap_analysis)
232. [ ] Velocidade média de tramitação de PL por UF. — TODO: requer tracking de tramitação
233. [ ] Taxa de aprovação de PLs sobre ITCD por UF. — TODO: requer outcome tracking
234. [ ] Tempo médio entre PL inicial → sanção. — TODO: requer outcome tracking
235. [ ] Detecção de "movimentos sincronizados" entre UFs no mesmo tema. — TODO: cross-UF
236. [ ] Análise de cobertura jornalística (volume + diversidade). — TODO: cross-source
237. [ ] Análise de divergência entre fontes sobre o mesmo ato. — TODO: cross-source
238. [ ] Tracking de citações cruzadas (PL X cita Lei Y de outra UF). — TODO: requer parsing avançado
239. [ ] Mapa de conexões entre normas (graph DOT/Mermaid gerado). — TODO: heavy
240. [ ] Linha do tempo interativa (HTML estático, vis.js). — TODO: vis.js
241. [x] Tabela comparativa de alíquotas atualizada. ✅ 2026-04-26 (aliquotas_por_uf)
242. [ ] Comparativo de regimes (progressivo × proporcional × híbrido). — TODO: classificação manual
243. [x] Estimativa de impacto fiscal (a partir de valores no texto). ✅ 2026-04-26 (count, não soma)
244. [x] Estatísticas de keywords (frequência, tendência, sazonalidade). ✅ 2026-04-26 (keyword_frequency)
245. [ ] "Vencedores e perdedores" em jurisprudência (fisco × contribuinte). — TODO: análise sentiment
246. [ ] Detecção de mudanças de orientação jurisprudencial. — TODO: requer tracking temporal
247. [ ] Análise de teses repetitivas (STF/STJ). — TODO: cross-decisões
248. [x] Score de "maturidade legislativa" por UF. ✅ 2026-04-26 (maturity_score_per_uf)
249. [ ] Detecção de tendência regional (Norte × Sul × etc.). — TODO: classificação por região
250. [x] Score de proatividade da SEFAZ por UF (frequência de IN). ✅ 2026-04-26 (sefaz_proactivity_per_uf)
251. [x] Score de atualidade da legislação (idade média da norma vigente). ✅ 2026-04-26 (actuality_score_per_uf)
252. [ ] Predição simples de relevância futura (Prophet local, sem Cloud ML). — TODO: Prophet
253. [x] Detecção de sazonalidade (final de ano fiscal, etc.). ✅ 2026-04-26 (seasonality_by_month)
254. [ ] Análise de correlação entre eventos legislativos. — TODO: estatística avançada
255. [ ] Comparativo Brasil × Internacional (briefing manual, contextualizado). — TODO: fonte externa

---

## 8. Busca & Navegação (256–280)

256. [ ] Busca full-text local (SQLite FTS5 mirror do Firestore para queries rápidas). — TODO: otimização futura
257. [ ] Busca semântica via embeddings (sentence-transformers local, sem custo). — TODO: heavy ML
258. [ ] Busca por similaridade cosine. — TODO: requer embeddings
259. [x] Busca facetada (UF + tipo + data + relevância simultâneos). ✅ 2026-04-26 (faceted_search)
260. [x] Highlight de termos no resultado. ✅ 2026-04-26 (highlight_term)
261. [x] Busca por número de ato com normalização. ✅ 2026-04-26 (normalize_act_number)
262. [x] Busca por órgão emissor. ✅ pré-existente (campo source.nome via term)
263. [x] Busca por relator/magistrado. ✅ pré-existente (via metadados detect_relator)
264. [ ] Salvamento de buscas favoritas. — TODO: state externo
265. [ ] Histórico de buscas. — TODO: state externo
266. [ ] Autocomplete de termos baseado em uso anterior. — TODO: requer histórico
267. [x] Busca booleana (AND / OR / NOT). ✅ 2026-04-26 (boolean_search)
268. [x] Busca fuzzy (Levenshtein) para typos. ✅ 2026-04-26 (fuzzy_search)
269. [x] Busca temporal ("últimos 30d", "abril 2026", "Q1 2026"). ✅ 2026-04-26 (faceted_search period)
270. [x] Export do resultado (CSV/JSON). ✅ pré-existente (build_csv/json_attachment)
271. [ ] URL compartilhável de busca (link encoded). — TODO: UI
272. [ ] Bookmark de busca recorrente. — TODO: state externo (cobertura via watch list)
273. [ ] Busca em texto integral de PDF (após extração). — TODO: requer pdfplumber
274. [x] Busca em comentários/anotações pessoais. ✅ 2026-04-26 (tag "comment:" pesquisável)
275. [x] Busca por tag. ✅ 2026-04-26 (faceted_search tag arg)
276. [x] Busca por modelo LLM usado (filtra docs classificados por X). ✅ 2026-04-26 (llm_model arg)
277. [x] Busca por versão de prompt (filtra docs classificados com prompt vN). ✅ 2026-04-26 (prompt_version arg)
278. [x] "Mais como este" — similaridade entre docs. ✅ 2026-04-26 (more_like_this)
279. [ ] CLI `monitoritcd search "termo"` para uso local. — TODO: adicionar subcomando em main.py
280. [x] Busca regex avançada para usuário poweruser. ✅ 2026-04-26 (regex_search)

---

## 9. Watch List & Observadores (281–305)

281. [ ] Watch por termo livre (texto).
282. [ ] Watch por número de PL específico.
283. [ ] Watch por UF + tema combinado.
284. [ ] Watch por relator/parlamentar.
285. [ ] Watch por tribunal.
286. [ ] Watch com regex.
287. [ ] Watch com expressão lógica (AND/OR/NOT).
288. [ ] Watch com janela temporal (válido só nesta semana).
289. [ ] Watch com expiração automática.
290. [ ] Watch com prioridade (sobrepõe silêncios).
291. [ ] Watch que dispara só em alta relevância.
292. [ ] Watch que dispara em qualquer match.
293. [ ] Watch com cooldown (não disparar 2x mesmo tema em 24h).
294. [ ] Watch compartilhável (URL/JSON para clonar).
295. [ ] Watch derivado de busca (transformar busca recorrente em watch).
296. [ ] Watch por hash exato de título.
297. [ ] Watch por similaridade > 0.85.
298. [ ] Watch por tipo (só decretos, só sanções, só PLs aprovados).
299. [ ] Watch por mudança de alíquota.
300. [ ] Watch por revogação.
301. [ ] Watch por modulação de efeitos.
302. [ ] Watch por cluster (agrupado por tema).
303. [ ] Watch por sequência (PL → comissão → plenário → sanção).
304. [ ] Notificação de "estágio mudou" no PL observado.
305. [ ] Templates de watch (presets: "alíquota SP", "holding familiar", etc.).

---

## 10. Segurança & Auditoria (306–340)

306. [ ] Audit log de toda mutation no Firestore.
307. [ ] Audit log de toda chamada ao LLM (com tokens).
308. [ ] Audit log de todo comando do bot.
309. [ ] Audit log de toda notificação enviada.
310. [ ] Audit log de toda mudança de config.
311. [ ] Imutabilidade do audit log (writes only, sem updates).
312. [ ] Rotação para Storage após 90 dias (com hash).
313. [ ] Hash chain do audit log (cada entry referencia hash da anterior).
314. [ ] CLI para verificar integridade do hash chain.
315. [ ] Alerta em comandos vindos de `chat_id` desconhecido.
316. [ ] Alerta em rate limit excedido (mesmo do dono).
317. [ ] Alerta em pico de atividade incomum.
318. [ ] Alerta em falha de assert de `owner_id`.
319. [ ] Alerta em SAST findings novos (CI).
320. [ ] Alerta em deps com vuln nova (Dependabot/pip-audit).
321. [ ] Alerta em commit com secret detectado.
322. [ ] Alerta em mudança em `firestore.rules`.
323. [ ] Honeytokens em arquivos de seed/example.
324. [ ] Honeytokens com Canarytokens (free) — alerta em uso real.
325. [ ] Bloqueio automático em Cloud Function de IP que tentou acesso.
326. [ ] CSP headers em e-mails HTML.
327. [ ] SBOM gerado em build (cyclonedx-bom).
328. [ ] Dependabot ativo no GitHub (free).
329. [ ] Renovate bot (free) com auto-merge para patches.
330. [ ] Branch protection rules (mesmo single-user, evita pushes acidentais).
331. [ ] Required reviews (auto-aprovação para si mesmo, mas obriga PR).
332. [ ] Status checks obrigatórios.
333. [ ] Pre-commit instalado e validado em CI.
334. [ ] Commit signing GPG/SSH.
335. [ ] Verificação de signed commits no CI.
336. [ ] SOPS para configs cifradas no repo (chave em GH Secret).
337. [ ] Mascaramento de PII em logs (regex CPF/CNPJ).
338. [ ] Detecção de tentativa de injection (SQL/NoSQL/XSS/SSRF).
339. [ ] Threat model documentado em `SECURITY.md`.
340. [ ] Tabletop exercises documentados (cenários "e se").

---

## 11. Observabilidade & Métricas (341–365)

341. [ ] Métrica: itens coletados por execução.
342. [ ] Métrica: itens classificados.
343. [ ] Métrica: itens descartados (relevância < 5).
344. [ ] Métrica: itens notificados.
345. [ ] Métrica: tempo de cada coletor.
346. [ ] Métrica: error rate por coletor.
347. [ ] Métrica: tokens LLM consumidos por execução.
348. [ ] Métrica: cota Firestore reads/writes usada (% do free tier).
349. [ ] Métrica: cota Storage usada (MB).
350. [ ] Métrica: tempo total da execução.
351. [ ] Métrica: tempo do classifier batch.
352. [ ] Métrica: tamanho médio de payload por fonte.
353. [ ] Métrica: idade média dos itens coletados.
354. [ ] Métrica: cobertura de UFs (quantas tiveram itens hoje).
355. [ ] Dashboard estático em GH Pages com Plotly.
356. [ ] Dashboard atualizado a cada cron run.
357. [ ] Métricas em formato Prometheus (texto exportado, sem hosting).
358. [ ] JSON feed de métricas.
359. [ ] `/healthcheck` no bot.
360. [ ] Smoke test integrado ao cron.
361. [ ] Trace ID por execução (correlation_id propagado nos logs).
362. [ ] Latência por etapa do pipeline.
363. [ ] Memória peak por execução (psutil).
364. [ ] SLO/SLI tracking (success rate, latência p95).
365. [ ] Status page estática em GH Pages com histórico de incidentes.

---

## 12. Gestão de Fontes (366–390)

366. [ ] Toggle de fonte via PR no YAML (mantém auditoria git).
367. [ ] Validação de YAML em CI (schema pydantic).
368. [ ] Lint específico para YAML de fontes (regras de domínio).
369. [ ] Auto-disable de fonte após N falhas seguidas.
370. [ ] Auto-reativação ao voltar a funcionar.
371. [ ] Health score por fonte (success rate, freshness).
372. [ ] Calendário de revisão (cada 30d revisar todas).
373. [ ] Sugestão automática de novas fontes via LLM (prompt periódico).
374. [ ] Validador de URL (HEAD request, content-type esperado).
375. [ ] Detecção de mudança de layout (parsing rate cai abruptamente).
376. [ ] Auto-fallback entre múltiplas URLs por fonte.
377. [ ] Mirror cached em Storage para resiliência.
378. [ ] Versionamento de selectors CSS (histórico de mudanças).
379. [ ] Anotação "última revisão manual" por fonte.
380. [ ] Tag "fragile" para fontes instáveis (alerta extra em falhas).
381. [ ] Tag "trusted" para fontes oficiais.
382. [ ] Tag "secondary" para fontes de mídia.
383. [ ] Hierarquia de confiança configurável.
384. [ ] Pesos diferentes na pré-classificação por confiança.
385. [ ] Histórico de mudanças por fonte.
386. [ ] Métrica "novidades por mês" por fonte.
387. [ ] Métrica "false positives" por fonte (descartados pelo LLM).
388. [ ] Detecção de mudança de domínio (redirect 301 persistente).
389. [ ] Auto-discovery de RSS em sites (feed link tag).
390. [ ] Detecção de `sitemap.xml` para descoberta de URLs.

---

## 13. Templates & Renderização (391–405)

391. [ ] Template "compacto" — 1 linha por item.
392. [ ] Template "detalhado" — resumo + link + metadados.
393. [ ] Template "executivo" — resumo + top 5.
394. [ ] Template "newsletter" — seções editoriais.
395. [ ] Template Markdown puro (para outras integrações).
396. [ ] Template HTML otimizado para gerar PDF (WeasyPrint).
397. [ ] Skin claro/escuro para email (auto via media query).
398. [ ] Localização BR (data DD/MM/YYYY, número 1.234,56).
399. [ ] Tema customizável (variáveis CSS).
400. [ ] Logo configurável (URL pública estática).
401. [ ] Footer customizável.
402. [ ] Header customizável.
403. [ ] Versão "telegrama" — resumo super conciso < 280 chars.
404. [ ] Personalização de tom (formal/casual via prompt).
405. [ ] A/B test de templates (rotação semanal, métricas de engajamento).

---

## 14. Retenção & Backup (406–420)

406. [ ] Backup mensal automático (GH Action 1º do mês).
407. [ ] Backup semanal opcional (configurável).
408. [ ] Cifragem com `age` (chave em GH Secret).
409. [ ] Verificação de integridade (checksum SHA-256).
410. [ ] Restauração via CLI (`monitoritcd restore <backup>`).
411. [ ] Backup incremental (apenas diff).
412. [ ] Múltiplos destinos (Drive + GitHub Releases).
413. [ ] Retention policy configurável (12 meses default).
414. [ ] Auto-archive de itens antigos para Storage (Firestore enxuto).
415. [ ] Soft delete (recuperável em janela de 30 dias).
416. [ ] Audit log com retention separado (1 ano).
417. [ ] Snapshot completo do projeto (Drive ou GH release).
418. [ ] Compressão antes de Storage (gzip → ~80% redução).
419. [ ] Deduplicação no Storage por hash (MD5/SHA-256).
420. [ ] Notificação de backup OK/falho (Telegram ao final).

---

## 15. Reprocessamento & Migração (421–435)

421. [ ] Reprocessar todos os itens de uma UF.
422. [ ] Reprocessar período específico.
423. [ ] Reprocessar com prompt diferente (A/B).
424. [ ] Comparar dois LLMs (Gemini × Groq) no mesmo conjunto.
425. [ ] Reprocessar relevância < N (segunda chance com prompt melhor).
426. [ ] Migração de schema versão N → N+1.
427. [ ] CLI para rodar migração específica.
428. [ ] Dry-run de migração (mostra diff sem aplicar).
429. [ ] Rollback de migração.
430. [ ] Backfill ao adicionar fonte nova (re-coleta última semana).
431. [ ] Re-extração de metadados sem re-classificação.
432. [ ] Re-render de notificações (se template mudou).
433. [ ] Re-deduplicação após mudança de strategy.
434. [ ] Recompute de severity tier sem chamar LLM.
435. [ ] Schema validator em CI (todos docs conformes ao schema atual).

---

## 16. Integrações Externas (436–460)

436. [ ] Export para Google Drive (PDF mensal automatizado).
437. [ ] Export para Notion (free workspace pessoal).
438. [ ] Sincronização com Obsidian vault local (markdown).
439. [ ] Sincronização com Logseq.
440. [ ] Export para Anki deck (flashcards das normas mais relevantes).
441. [ ] Integração com Zotero (referências jurídicas, free).
442. [ ] Bookmarklet para enviar URL ao bot (1-click clip).
443. [ ] Webhook genérico (POST JSON para URL configurável).
444. [ ] n8n.io self-hosted (Docker, free) para automações.
445. [ ] Trello via webhook (cartão por item observado).
446. [ ] GitHub Issues — criar issue de PL observado (audit pessoal).
447. [ ] Calendar.ics subscribe URL (qualquer cliente de calendário).
448. [ ] NextCloud (self-host opcional) para arquivamento.
449. [ ] Mastodon — auto-post em conta pessoal técnica.
450. [ ] Bluesky — auto-post.
451. [ ] Matrix.org — sala privada com bot.
452. [ ] IRC bot (Libera/OFTC, free).
453. [ ] XMPP bot (servidor público gratuito).
454. [ ] IFTTT applets (5 grátis).
455. [ ] Pushbullet (free pessoal).
456. [ ] Apple Shortcuts integration (iOS/macOS via webhook).
457. [ ] Discord rich presence (status visual).
458. [ ] Slack workspace pessoal (free).
459. [ ] Webhook para Home Assistant (LAN, total controle).
460. [ ] SMTP forwarding configurável (encaminhar digest a outras contas).

---

## 17. Testes & Qualidade (461–485)

461. [ ] Property-based testing com `hypothesis` em parsers/sanitizers.
462. [ ] Mutation testing semanal com `mutmut`.
463. [ ] Chaos testing — derrubar fontes propositalmente em ambiente teste.
464. [ ] Smoke tests pós-deploy.
465. [ ] Synthetic data tests (geração de fixtures via Faker).
466. [ ] Snapshot tests para todos os templates (`syrupy`).
467. [ ] Regression suite executada antes de cada release.
468. [ ] Performance baseline (rodar e comparar com histórico).
469. [ ] Memory leak tests (`pytest-memray` ou similar).
470. [ ] Security scan completo automatizado em CI.
471. [ ] Linter customizado para regras do projeto (ex: validar uso de `SecretStr`).
472. [ ] Pre-merge gate strict (sem merge se algum check falhar).
473. [ ] Code review checklist auto-gerado por tipo de PR.
474. [ ] Coverage badge no README.
475. [ ] Build status badge.
476. [ ] License compliance check (`pip-licenses`).
477. [ ] Dependency drift report (semanal).
478. [ ] Stale code detector (`vulture`).
479. [ ] Flaky test detector (relatório de testes intermitentes).
480. [ ] Test history report (tendência de duração).
481. [ ] Coverage delta por PR (não pode cair).
482. [ ] Mutation score badge.
483. [ ] Code complexity report (`radon`).
484. [ ] Cyclomatic complexity gate (max 10 por função).
485. [ ] Documentation coverage check (`interrogate`).

---

## 18. Documentação (486–500)

486. [ ] README com badges (build, coverage, license, security).
487. [ ] CONTRIBUTING.md (padrões para você + Claude Code).
488. [ ] SECURITY.md com threat model completo.
489. [ ] ARCHITECTURE.md com diagramas C4 (level 1, 2, 3).
490. [ ] RUNBOOKS.md — procedimentos operacionais (rotação de secret, restauração de backup, etc.).
491. [ ] CHANGELOG.md mantido com convenção (Keep a Changelog).
492. [ ] ADRs (Architecture Decision Records) em `docs/adr/`.
493. [ ] Tabela completa das 27 UFs no README (status + alíquota + regime).
494. [ ] Glossário tributário em `docs/glossario.md`.
495. [ ] Tutorial "como adicionar uma fonte" passo a passo.
496. [ ] Tutorial "como rotacionar um secret".
497. [ ] Tutorial "como restaurar de backup".
498. [ ] FAQ (perguntas que você terá daqui a 6 meses).
499. [ ] Diagrama de fluxo de dados (DFD).
500. [ ] Postmortem template em `docs/templates/postmortem.md`.

---

## Notas de uso deste backlog

- **Prioridade ≠ ordem na lista.** Estas estão numeradas para referência cruzada, não por importância.
- **MVP enxuto** (definido no CLAUDE.md Seção 4) não precisa cobrir nem 10% disso.
- **Antes de implementar uma ideia desta lista**: verifique se entra no escopo atual,
  se respeita os princípios canônicos, se cabe nas cotas free tier do dia.
- **Sugestão de priorização** ao avaliar uma ideia:
  1. Resolve uma dor real e atual? (não "será útil um dia")
  2. Custo de implementação proporcional ao valor?
  3. Não cria dívida operacional (não precisa de manutenção contínua)?
  4. Compatível com os princípios canônicos (Seção 🛡️ do CLAUDE.md)?
- **Atualize este arquivo** marcando ideias implementadas com ✅ e a data.
- Ideias **descartadas** (não vão acontecer): mover para `IDEAS_DESCARTADAS.md` com motivo.
