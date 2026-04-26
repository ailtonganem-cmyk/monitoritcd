# ADR 0002 — LLM provider: Gemini primário, Groq fallback

**Status**: Accepted
**Data**: 2026-04-26 (registro retroativo — Sugestão #39)

## Contexto

O sistema precisa classificar (tipo, relevância, severity tier, resumo)
documentos coletados de fontes públicas. Single-user, sem orçamento para
APIs pagas em volume.

Restrições:
- Custo zero ou tier free generoso.
- Cota suficiente para ~50-200 itens/dia (após pré-filtro de keywords + prescore).
- Suporte a JSON estruturado com schema validation.
- Latência tolerável (cron diário, não interativo).

## Decisão

- **Primário**: Google Gemini 2.5 Flash (15 RPM, 1.500 req/dia free).
- **Fallback**: Groq Llama 3.3 (em quota error do Gemini).
- Wire via `FallbackLLMProvider` em `src/monitoritcd/llm/fallback.py`.

## Consequências

**Positivas**:
- Free tier suficiente para escala atual.
- Resposta JSON nativa em ambos.
- Fallback automático evita perda de itens em quota peak.
- LLM sempre opcional: pipeline funciona sem quando ambos falham (DLQ).

**Negativas**:
- Dependência de provedor externo (com TOS sujeito a mudança).
- Modelos diferentes entre primário e fallback → diferenças sutis de saída.
- Mitigado por `extra="forbid"` no pydantic schema (rejeita drift).

## Alternativas consideradas

- **OpenAI GPT-4o-mini**: pago. Rejeitado.
- **Claude Haiku 4.5**: pago. Rejeitado.
- **Modelo local (Ollama)**: latência alta, GH runner não tem GPU. Rejeitado.
- **Sem LLM (regex pura)**: insuficiente para `tipo` + `resumo`. Rejeitado.

## Referências

- `src/monitoritcd/llm/fallback.py`
- `src/monitoritcd/filters/llm_classifier.py:46` (PROMPT_VERSION)
