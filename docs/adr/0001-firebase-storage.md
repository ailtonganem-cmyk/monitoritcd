# ADR-0001: Firebase como storage primário

**Data**: 2026-04-26
**Status**: Accepted
**Decisores**: Dono (single-user)

## Contexto

Sistema single-user precisa de storage persistente para:
- Metadados de documentos coletados (~50 MB/ano)
- Conteúdo bruto HTML/PDF (~500 MB/ano)
- Audit log com retenção 1 ano
- Configuração de UFs ativas / silenciamentos
- Watch list

Restrições:
- **Custo zero** (ou near-zero); Spark plan suficiente.
- Sem manutenção de servidor.
- Backup e restore simples.
- Sem operações > 50K writes/dia, 50K reads/dia.

## Opções avaliadas

### A) PostgreSQL (Supabase free tier)
- ✅ SQL conhecido, queries flexíveis
- ❌ 500 MB limit; 2 projetos ficam dormentes em 7 dias
- ❌ Setup adicional para storage de PDFs

### B) Firebase (Spark)
- ✅ Firestore + Storage no mesmo projeto
- ✅ 1 GB Firestore + 5 GB Storage no free tier
- ✅ Cloud Functions para webhooks + proxy BR
- ✅ Backup nativo via export
- ❌ Vendor lock-in
- ❌ NoSQL (queries complexas mais difíceis)

### C) SQLite + GitHub releases
- ✅ Simplicidade extrema
- ❌ Sem real-time read; backup acopla ao deploy
- ❌ Limit de release size 2 GB

## Decisão

**Adotamos Firebase (Spark)** — opção B. Motivos:

- Free tier generoso e estável (1 GB Firestore + 5 GB Storage = ~10 anos de dados).
- Cloud Functions complementam (proxy BR para fontes geo-restricted, webhook bot).
- Backup mensal automatizado via export (cifrado com `age`).
- App Check disponível para defense-in-depth contra service account leaks.

## Consequências

- **Positivas**: stack unificada, custo zero, deploy via firebase CLI.
- **Negativas**: vendor lock-in com Google; queries NoSQL exigem padrões específicos.
- **Mitigações**: storage abstraído por `StorageProtocol` (in-memory para testes, Firestore para prod). Migração futura possível se Firebase mudar tier.

## Princípios canônicos respeitados

- Princípio 1: validação anti-SSRF + Pydantic em toda escrita.
- Princípio 3: service account JSON via env var, nunca em código.
