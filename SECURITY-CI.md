# Segurança no CI — proposta v3 (decisão do Ailton, 17/10/2026)

Perfil: API/DAT (Python, Cloud Functions) · referência · Tier: T3 · Visibilidade: público

- Segurança: ASVS L2 · MASVS n/a · LLM/Agentic n/a · ameaças: docs/ameacas.md (SEGURANCA-001, bot do projeto)
- CodeQL: roda em `seguranca-pr.yml` (repo público)

## O que roda
| Onde | Workflow | Conteúdo |
|---|---|---|
| PR / push main / semanal | `seguranca-pr.yml` | zizmor, actionlint, Semgrep `--error` (p/default; nunca `--config auto`), OSV-Scanner, gitleaks `--redact`, Trivy mitigado, CodeQL; agregador `seguranca-ok` reprova job pulado/falho (D-02) |
| Semanal (dom 07:00 UTC) | `seguranca-agendada.yml` | trufflehog `--only-verified`, OpenSSF Scorecard (sem publicar), ZAP full + Nuclei sem intrusivos (só HML), fuzz 1 h |

## Regras aplicadas
- Toda `uses:` fixada por SHA completo com comentário da versão; imagens por digest; Renovate (`renovate.json`) com quarentena `minimumReleaseAge: 1 day` e caminho rápido sem quarentena para alertas de vulnerabilidade/categoria `security` (D-06/D-07).
- `permissions: contents: read` no topo de cada workflow; elevação só por job (ex.: Scorecard `actions: read`, CodeQL `security-events: write`). Checkouts com `persist-credentials: false`.
- Trivy (D-01/D-08): `aquasecurity/trivy-action` v0.36.0 por SHA, binário Trivy v0.76.0 baixado e verificado com `cosign verify-blob` (identidade do workflow de release da Aqua) antes de usar (`skip-setup-trivy`), `--scanners vuln,misconfig` (segredos = gitleaks/trufflehog), sem segredos/tokens, em `ubuntu-latest` hospedado.
- Jobs novos de segurança rodam em runner hospedado descartável, sem segredos. Jobs existentes mantêm seus runners.

## Jobs condicionados (sem alvo = não verificado; ligar por variável de repositório)
| Variável | Liga | Observação |
|---|---|---|
| `HML_URL` | ZAP full scan + Nuclei | Só URL de homologação acessível pela internet; nunca produção (D-21). |
| `FUZZ_ENABLED=true` | fuzz 1 h | Requer script npm `fuzz` e corpus versionado (D-26). |


Enquanto a variável não existir o job aparece como pulado: isso é **não verificado** pela §9.2 e fica registrado aqui como lacuna.

## Pendências / n/a
- Renovate: o app precisa estar instalado na conta para o `renovate.json` ter efeito.
- Regras Semgrep locais do template (sinks XSS, `pull_request_target`, MCP, PII) virão do `_template-projeto` (Grok Skill, §11 item 1); até lá `p/default`.
- Push protection de segredos: depende de GHAS em repo privado.
- CodeQL já roda em `codeql.yml` (repo público); não duplicado em `seguranca-pr.yml`. Scorecard já roda em `scorecard.yml`.
- `security.yml` (bandit, gitleaks-action, detect-secrets, pip-audit, SBOM) mantido; perdeu `security-events: write` no topo (nenhum job sobe SARIF).
- Coexistem `dependabot.yml` e `renovate.json`: decidir qual fica para não duplicar PRs.
- zizmor aponta achados reais pré-existentes: injeção de template em `digests.yml`, `monitor.yml`, `reprocess.yml`, `actionlint.yml`; permissões amplas e gatilho perigoso em `pages.yml`; `actionlint.yml` baixa script da branch `main` do actionlint via curl|bash (sem pin).
