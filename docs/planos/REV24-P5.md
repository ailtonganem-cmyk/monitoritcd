# REV24-P5 — gitleaks.toml sem literais de canário e sem regex global de chave privada; baseline sem allowlist

Projeto: MonitorITCD · Tier T2 · Nível S1 · criado em 2026-10-24 pela revisão do método (Rodada 4). Não implementado: fica para o agente da próxima sessão neste projeto.

## Objetivo

gitleaks.toml sem literais de canário e sem regex global de chave privada; baseline sem allowlist.

## Situação conferida

.gitleaks.toml tem literais de canário AWS e regex global 'PRIVATE KEY'; .secrets.baseline marca 19 hex como não segredo (PR #75).

## Passos

- [ ] Remover os literais e o regex global (o canário fica só no arquivo de teste).
- [ ] Trocar o baseline pela correção na origem: hashes prefixados no validar.json (tarefa do método no Skill).

## Arquivos envolvidos

- `.gitleaks.toml`
- `.secrets.baseline`

## Critério de aceite e testes

Dado a main, quando `gitleaks dir .` e `detect-secrets scan` rodam, então não há achado nem allowlist.

Merge só por `gh pr merge --auto` (o GitHub mescla depois do helios/homologar). `fix:` com teste de regressão.

## Revisão

(preencher ao concluir)
