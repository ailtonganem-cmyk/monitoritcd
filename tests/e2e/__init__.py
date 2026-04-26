"""E2E tests — smoke do pipeline completo (Sugestão #12).

Roda em CI semanal (não bloqueia PR), com InMemoryStorage + FakeLLM
(zero dependência externa). Garante que o `--dry-run` continua executando
end-to-end mesmo após refatorações.
"""
