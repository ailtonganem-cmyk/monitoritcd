# Runbook — Excesso de emails do canarytokens.org

> Solução **definitiva** para o ruído de emails do honeytoken plantado em
> `scripts/legacy_aws_loader.py` (desativado em 2026-04-26).

## Contexto

O honeytoken AWS plantado no repo público disparava canarytokens.org cada vez
que um scanner automatizado tentava validar a chave `AKIA...`. Resultado:
caixa de entrada do dono inundada de emails.

A **Camada 1** da solução (sanitizar o repo) **já foi feita pelo PR que
introduziu este runbook**. As camadas 2 e 3 abaixo são ações manuais que
**você precisa executar uma vez** para parar definitivamente os emails.

---

## Camada 2 — Apagar o canary em canarytokens.org

**Por que**: mesmo após sanitizar o repo, o token AWS plantado no histórico
Git continua válido no canarytokens.org. Scanners que clonam histórico
completo (ex: trufflehog com `--no-history=false`) ainda podem dispará-lo.

### Passo a passo

1. Procure no Gmail o **email original de criação do canarytoken** (foi
   recebido em 2026-04-25 no email do dono). Assunto típico: "Your new
   Canarytoken has been created".

2. No corpo do email, há link "**Manage this Canarytoken**". Clique.

3. Na página de gerenciamento, há botão "**🗑️ Delete this token**".

4. Confirme. O token deixa de ser válido — qualquer scan futuro retornará
   401 do AWS STS sem disparar alerta.

### Alternativa: manter o canary ativo, mas via webhook (não recomendado)

Se quiser preservar o canary para detecção (apesar do custo de ruído já
demonstrado):

1. "Manage this Canarytoken" → tab **Webhook**.
2. URL: `https://canary-filter-XXX.run.app/?token=<CANARY_FILTER_TOKEN>`
   (a URL real está em `gcloud functions describe canary_filter --region=us-central1`).
3. Save.
4. Tab **Email** → **Disable**.
5. Resultado: zero email; Cloud Function `canary_filter` filtra scanners
   conhecidos por User-Agent/IP e só notifica via Telegram quando trigger
   parece humano real.

> Risco residual: se canary-filter Cloud Function ficar fora do ar, alertas
> se perdem silenciosamente. Para sistemas single-user com baixo valor de
> detecção, a opção "Delete this token" é mais simples e definitiva.

---

## Camada 3 — Filtro Gmail server-side (defesa em profundidade)

**Por que**: caso futuramente o canary seja recriado por engano e esqueça
de configurar webhook-only, este filtro garante que os emails nunca
atrapalhem a inbox.

### Passo a passo

1. Acessar Gmail no navegador → ícone de engrenagem → "Ver todas as
   configurações".

2. Aba "**Filtros e endereços bloqueados**" → "**Criar um novo filtro**".

3. Preencher:
   - **De**: `noreply@canarytokens.org`
   - (alternativa, mais agressiva): `*@canarytokens.org`
   - **Tem as palavras**: `canarytoken triggered`

4. Clicar "**Criar filtro**".

5. Marcar:
   - ☑ **Pular caixa de entrada (arquivar)**
   - ☑ **Marcar como lido**
   - ☑ **Aplicar marcador**: `canary-noise` (criar marcador novo se não existir)
   - ☑ **Nunca enviar para spam**
   - ☑ **Aplicar também aos N e-mails correspondentes** (limpa o backlog)

6. Salvar.

**Resultado**: emails do canarytokens.org continuam sendo recebidos (você
pode auditar buscando `label:canary-noise`), mas não aparecem na inbox
nem geram notificação push do Gmail.

---

## Verificação pós-execução

Depois de executar Camadas 2 e 3:

1. Aguardar 24h.
2. Procurar `label:canary-noise` no Gmail — espera-se zero novos
   (Camada 2 deletou o token).
3. Caso ainda apareça algum email novo:
   - Confirmar que o token foi de fato deletado em canarytokens.org.
   - Confirmar que o filtro Gmail está ativo.
   - Verificar se há **outro** canary plantado em algum lugar do repo:
     `git grep -i 'canarytoken\|honeytoken'`.

## Histórico

- **2026-04-25**: honeytoken AWS plantado (T8 ativo).
- **2026-04-26**: honeytoken removido do repo (T8 desativado em SECURITY.md);
  este runbook criado para guiar a desativação no canarytokens.org.

## Referências

- [SECURITY.md](../../SECURITY.md) — seção T8 (DESATIVADO) e T10 (canary_filter).
- [functions/canary_filter/main.py](../../functions/canary_filter/main.py) —
  Cloud Function de filtro (mantida por enquanto, inerte).
- [Canarytokens.org docs](https://docs.canarytokens.org/) — documentação oficial.
