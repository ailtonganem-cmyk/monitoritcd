# 50 — Saídas: e-mail, Telegram e bot (a "UI" do sistema)

> Fonte da verdade das **superfícies visíveis ao dono**. O MonitorITCD é
> headless: não há frontend web. A interface humana são os **templates de e-mail
> Jinja2**, as **mensagens do Telegram** e os **comandos do bot** — e eles são
> tratados como UI, com snapshot test obrigatório (`70`).
>
> *Este módulo substitui o `50-frontend.md` genérico do template, inaplicável a
> um sistema sem frontend (decisão do dono 2026-08-13).*

## Severity tiers — o contrato de atenção do dono

A relevância 0-10 devolvida pelo LLM (`40`) mapeia em tier, e o tier decide o
canal. Mudar esse mapeamento é decisão de produto (`90`), não ajuste técnico.

| Tier | Significado | Entrega |
| --- | --- | --- |
| 🔴 Crítico | muda a regra aplicável agora | push imediato no Telegram |
| 🟠 Alta | relevante, exige leitura no dia | digest, em destaque |
| 🟡 Normal | acompanhamento | digest |
| 🟢 Baixa | registro | digest semanal |
| — Descartado | fora dos 3 tópicos | não notifica; purga em 90 dias |

Racional e histórico: `docs/adr/0003-severity-tiers.md`.

## E-mail (Jinja2)

- `autoescape=True` **sempre** — conteúdo coletado é entrada hostil (`60`).
- CSP no `<head>`; CSS inline (clientes como o Gmail descartam `<style>`).
- HTML validado (`html5lib`); nada de dependência externa remota no corpo.
- Canal **opcional**: credencial ausente desliga o e-mail e **não** derruba a
  coleta nem o Telegram (decisão registrada em `00`).
- Conteúdo verbatim da fonte; o campo `contexto` aparece **rotulado como gerado
  por IA**, visualmente separado do resumo factual (`40`).

## Telegram

- **Escape MarkdownV2 obrigatório** antes de enviar
  (`_ * [ ] ( ) ~ > # + - = | { } . !`) — via `security/markdown_escape.py`,
  nunca à mão no call site.
- **Split em 4096 caracteres**: dividir antes de enviar, preservando blocos.
- Emoji de tier como primeiro caractere da linha de título — é o índice visual
  do dono.
- Link da fonte sempre presente; o resumo, porém, deve bastar sem abrir o link.

## Bot — comandos suportados

| Comando | Função |
| --- | --- |
| `/start` | Saudação + lista de comandos |
| `/status` | Última coleta, fontes ativas/falhando, cota de LLM restante |
| `/buscar <termo> [UF] [ano]` | Busca em `documento/` por título/resumo |
| `/observar <termo>` · `listar` · `remover <id>` | Watch list (alerta imediato em match futuro) |
| `/marcar <doc_id> <tag>` | Tag pessoal num documento |
| `/silenciar <UF> <duração>` | Mute temporário |
| `/estados listar` · `ativar <UF>` · `desativar <UF>` | Gerencia UFs ativas (`40`) |
| `/relatorio [diario\|semanal]` | Digest sob demanda |

- Arquitetura: Telegram → webhook → Cloud Function `bot_webhook` → handler
  Python. **Nunca polling.**
- **A validação da entrada do bot é matéria do módulo `60`** (identidade,
  schema, rate limit) — aqui trata-se só da apresentação.
- **Ação destrutiva exige confirmação em 2 passos** (token efêmero de 60 s,
  single-use).
- Cold start de 2-5 s na primeira chamada do dia é esperado — não é bug.
- Mudança em `src/` que afete o bot **exige redeploy da Cloud Function**: ela
  instala `monitoritcd` a partir do branch principal, não do working tree.

## Mensagens de erro ao dono

Genéricas na superfície ("falha ao coletar a fonte X"), completas no log
estruturado. Nunca expor token, URL assinada, stack trace bruto ou payload da
fonte numa mensagem de e-mail/Telegram (`60`, `90`).

## Regra de mudança

Todo template tem **snapshot test** (`syrupy`): alterar a saída exige aprovação
explícita do snapshot no mesmo trabalho. Edge cases obrigatórios na suíte: corpo
vazio, volume alto de itens, caracteres especiais, emoji, texto RTL, título no
limite de tamanho.
