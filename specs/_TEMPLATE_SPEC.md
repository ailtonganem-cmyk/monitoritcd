# SPEC \<ID> — \<título curto>

> Modelo da **SPEC de Execução** (`regras/10-metodo-trabalho.md`). Copie para
> `specs/SPEC_<ID>_<slug>.md`, preencha e ratifique **antes** de qualquer
> edição de código. Seção material vazia = despacho devolvido pelo executor.
> A SPEC é versionada no git e entra no commit da tarefa.

## Identificação

- **ID / slug:** `<id>` · `<slug>`
- **Porte:** trivial | média | grande (`regras/10-metodo-trabalho.md` — escala por risco)
- **Worktree:** `../MonitorITCD-worktrees/<id>` · branch `tarefa/<id>`
- **Orquestrador:** `<sessão/modelo>`
- **Executor previsto:** complexo (`opus`) | simples (`sonnet`) — `regras/20-orquestracao-modelos.md`
- **MCPs/CLIs a utilizar:** `<Firebase, gh, gcloud, Chrome DevTools… ou "nenhum">`

## Problema e objetivo

`<o que está errado ou falta, e qual o resultado esperado — em uma frase cada>`

## Escopo

- **Dentro:** `<o que será feito>`
- **Fora:** `<o que explicitamente NÃO será feito nesta tarefa>`

## Mapa de arquivos

| Arquivo | O que muda |
| --- | --- |
| `<caminho>` | `<mudança>` |

## System design

`<como a solução se encaixa na arquitetura existente; contratos, tipos, fluxo de
dados; o que já existe e será reaproveitado>`

## Decisões e alternativas descartadas

- **Decisão:** `<escolha>` — **porquê:** `<motivo>` — **descartado:** `<alternativa e por quê>`

## Métodos e melhores práticas obrigatórias

`<regras dos módulos que incidem: input_limits (60), sanitização (60), fatos
protegidos (40), snapshot de template (50), verbatim do original (40)…>`

## Plano de execução

1. `<passo>`
2. `<passo>`

## Riscos e armadilhas

`<riscos desta mudança + armadilhas aplicáveis de regras/70-testes-validacao.md>`

## Critério de aceite

- [ ] `<condição objetiva e verificável>`

## Plano de validação (gates a rodar)

```bash
<comandos exatos — regras/70-testes-validacao.md>
```

## Evidência exigida no relatório

`<saída literal de quais gates, qual prova empírica: --dry-run, documento
gravado, e-mail renderizado, mensagem do Telegram…>`

## Registro do R (revisão do plano)

`<furos encontrados na revisão adversarial do plano e como foram resolvidos;
conflitos com as NUNCAs verificados>`
