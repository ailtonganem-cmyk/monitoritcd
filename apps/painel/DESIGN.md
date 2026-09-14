# Design System: MonitorITCD Painel

Painel interno de operação (uma pessoa). Visual de ferramenta jurídica-administrativa: denso o bastante para tabelas, sem estética de startup genérica.

## 1. Atmosfera

Estúdio de despacho: claro, quieto, preciso. Density 6, variance 4, motion 4. Não é landing page. Não é hero assimétrico. É software de trabalho.

## 2. Cores

- **Papel** (#F4F1EA) — fundo da aplicação
- **Superfície** (#FFFdf8) — cards, tabela, dialogs
- **Tinta** (#1C1917) — texto principal (stone-900, nunca #000)
- **Anotação** (#78716C) — secundário, labels, metadados
- **Linha** (#E7E5E4) — bordas 1px
- **Selo** (#3F5C4B) — único acento (verde-musgo dessaturado). CTAs, nav ativa, foco
- **Alerta** (#9A3412) — exclusão / erro, não como acento de marca

Proibido: roxo neon, azul elétrico, gradiente em título, glow.

## 3. Tipografia

- **UI:** "Source Sans 3" (Google Fonts) — títulos 600, corpo 400, line-height 1.5
- **Mono:** "IBM Plex Mono" — IDs de fonte, URLs, comandos
- Proibido: Inter, Roboto como display, serif em dashboard

## 4. Componentes

- **Login:** uma coluna, max 28rem, no centro do papel. Marca + uma frase + um botão Google. Sem card Material genérico inchado.
- **Shell:** barra superior no tom Selo, texto claro, nav com estado ativo óbvio. Conteúdo max-width 1200px, padding clamp(1rem, 3vw, 2rem).
- **Botões:** primário preenchido Selo; perigo outline/warn. Altura mínima 44px no toque.
- **Tabela:** superfície, cabeçalho sticky se couber, linhas com hover sutil, sem elevation-z8 genérico.
- **Campos:** label acima, densidade confortável.
- **Vazio:** uma linha dizendo o que fazer, sem ilustração stock.

## 5. Layout

Mobile: nav vira menu compacto; tabela com scroll horizontal só nas colunas de dados, página sem overflow da viewport. Desktop: nav horizontal.

## 6. Movimento

Só opacity/transform, 150–220ms. Sem loop infinito, sem spinner genérico como único feedback (pode haver estado "Entrando…").

## 7. Conteúdo

Português brasileiro. Não inventar lei, alíquota, ementa. Allowlist visível: `ailtonganem@gmail.com`. Título do documento: MonitorITCD.
