"""Classifier LLM — Filtro 2.

Usa Gemini 2.5 Flash (primary) ou Groq Llama (fallback) para classificar
itens pré-aprovados. Output validado por pydantic com `extra="forbid"`.

Princípios canônicos materializados:
1. **LLM NÃO MODIFICA dados originais** (Seção 5 do CLAUDE.md). O LLM gera
   metadados/resumo SOBRE o conteúdo, sem substituir.
2. **input_limits** aplicados via `LLMResult` (max_length em resumo, etc.).
3. **Backend não confia**: response do LLM passa por pydantic (extra=forbid).
4. **Prompt versão registrada** em `LLMResult.llm_prompt_version` para
   reprocessamento futuro.

Estratégia anti-quota:
- Batch de até `MAX_BATCH_LLM` itens em uma única call.
- Pré-filtro (keywords + prescore) elimina ≥ 80% antes do LLM.
- Fallback Groq quando Gemini estoura cota (15 RPM, 1500/dia).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

import structlog
from pydantic import ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitoritcd.core import limits
from monitoritcd.core.models import LLMResult, SeverityTier, TipoAto, Topic

if TYPE_CHECKING:
    from collections.abc import Sequence

    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

# Versão do prompt: bump major em mudanças de schema, minor em ajustes.
PROMPT_VERSION = "v1.0"

# Mapeamento determinístico relevância → severity tier.
SEVERITY_THRESHOLDS = (
    (limits.RELEVANCIA_THRESHOLD_CRITICO, SeverityTier.CRITICO),
    (limits.RELEVANCIA_THRESHOLD_ALTA, SeverityTier.ALTA),
    (limits.RELEVANCIA_THRESHOLD_NORMAL, SeverityTier.NORMAL),
    (limits.RELEVANCIA_THRESHOLD_BAIXA, SeverityTier.BAIXA),
)

SYSTEM_PROMPT = """Você é um classificador de atos legislativos, normativos e jurisprudenciais
brasileiros sobre 3 áreas correlatas:

1. **ITCD/ITCMD/ITD** — Imposto sobre Transmissão Causa Mortis e Doação (tributário).
2. **Direito das Sucessões** — Direito Civil (CC arts. 1.784+): herança, testamento,
   inventário, partilha, herdeiros necessários, deserdação, união estável, etc.
3. **Regime de Bens** — Direito Civil (CC arts. 1.639-1.688): comunhão parcial/universal,
   separação, pacto antenupcial, alteração de regime, Súmula 377, etc.

REGRAS INEGOCIÁVEIS — você DEVE obedecer SEMPRE:
1. NÃO modifique nomes próprios, números de atos, datas ou cifras. Preserve verbatim.
2. NÃO anonimize partes mencionadas. Mantenha como aparece no texto original.
3. NÃO infira fatos não explícitos no texto. Se não souber, deixe null/empty.
4. NÃO parafraseie de forma que altere sentido. O resumo deve ser factual.
5. RESUMO: 1 a 3 frases curtas, em PT-BR, descrevendo o ato/decisão objetivamente.

Para cada item da lista, retorne um objeto JSON com EXATAMENTE estas chaves:

{
  "tipo": "<um de: projeto_lei, lei_sancionada, decreto, instrucao_normativa,
           portaria, noticia, jurisprudencia, doutrina, outro>",
  "topics": ["<um ou mais de: itcd, sucessoes, regime_bens>"],
  "relevancia": <integer 0-10>,
  "resumo": "<1-3 frases factuais em PT-BR>",
  "numero_ato": "<ex: 1234/2026 ou null>",
  "orgao_emissor": "<ex: SEFAZ-SP, STF, ou null>",
  "tags": ["tag1", "tag2"]
}

`topics` deve incluir **todas** as áreas tocadas pelo item:
- "itcd" se discute alíquota, base de cálculo, fato gerador, IN tributária.
- "sucessoes" se discute herança, testamento, inventário, herdeiros (mesmo sem ITCD).
- "regime_bens" se discute comunhão, separação, pacto, divórcio (mesmo sem ITCD).

Relevância:
- 9-10: mudança crítica de alíquota, decisão STF/STJ vinculante, súmula nova.
- 7-8:  IN/portaria nova, PL aprovado em comissão, acórdão relevante.
- 5-6:  notícias gerais, doutrina relevante.
- 0-4:  conteúdo tangencial.

Retorne EXCLUSIVAMENTE um JSON array. Nada mais. Sem comentários, sem markdown.
"""

# Limite de texto enviado por item ao LLM (ajuste conforme janela de contexto).
MAX_ITEM_TEXT_FOR_LLM: int = 3000


class LLMProvider(Protocol):
    """Interface mínima de um provedor de LLM."""

    name: str
    """Identificação do modelo (ex: `gemini-2.5-flash`). Vai parar em `LLMResult.llm_model`."""

    async def classify_batch(self, items_text: list[str]) -> list[dict[str, Any]]:
        """Recebe lista de textos, retorna lista de dicts (um por item)."""
        ...  # pragma: no cover - Protocol method body


def map_relevancia_to_tier(relevancia: int) -> SeverityTier:
    """Mapeia relevância 0-10 → severity tier."""
    if relevancia < limits.RELEVANCIA_THRESHOLD_DESCARTADO:
        return SeverityTier.DESCARTADO
    for threshold, tier in SEVERITY_THRESHOLDS:
        if relevancia >= threshold:
            return tier
    return SeverityTier.DESCARTADO  # pragma: no cover - inalcançável


def build_item_text(item: RawItem) -> str:
    """Monta texto para envio ao LLM. Inclui delimitador <context>."""
    texto = item.texto_raw or ""
    # Trunca texto longo — input_limits enforcement
    if len(texto) > MAX_ITEM_TEXT_FOR_LLM:
        texto = texto[:MAX_ITEM_TEXT_FOR_LLM] + "..."
    return f"<context>\nTítulo: {item.titulo_raw}\n\n{texto}\n</context>"


def parse_llm_response(
    raw_response: dict[str, Any],
    *,
    llm_model: str,
) -> LLMResult:
    """Valida response do LLM e constrói LLMResult.

    Princípio canônico 1: backend nunca confia — pydantic com extra=forbid.

    Args:
        raw_response: dict do JSON do LLM.
        llm_model: identificação do modelo usado (ex: "gemini-2.5-flash").

    Returns:
        `LLMResult` validado.

    Raises:
        ValidationError: se schema do LLM não corresponde.
        ValueError: se campos obrigatórios faltam.
    """
    tipo_str = raw_response.get("tipo", "outro")
    relevancia = raw_response.get("relevancia", 0)
    resumo = raw_response.get("resumo", "")
    if not resumo:
        msg = "LLM response sem resumo"
        raise ValueError(msg)

    metadados = {}
    if raw_response.get("numero_ato"):
        metadados["numero_ato"] = str(raw_response["numero_ato"])
    if raw_response.get("orgao_emissor"):
        metadados["orgao_emissor"] = str(raw_response["orgao_emissor"])

    tags = raw_response.get("tags") or []
    # Trunca tags excedentes por defesa (input_limits enforced no model)
    tags = [str(t)[: limits.MAX_TAG_LENGTH] for t in tags[: limits.MAX_TAGS_PER_DOC]]

    try:
        tipo = TipoAto(tipo_str)
    except ValueError:
        tipo = TipoAto.OUTRO

    rel_int = max(limits.RELEVANCIA_MIN, min(limits.RELEVANCIA_MAX, int(relevancia)))

    # Topics — defaulta a [ITCD] se LLM não retornar (compat).
    topics_raw = raw_response.get("topics") or [Topic.ITCD.value]
    topics: list[Topic] = []
    for t in topics_raw:
        try:
            topics.append(Topic(t))
        except ValueError:
            continue
    if not topics:
        topics = [Topic.ITCD]

    return LLMResult(
        classified_at=datetime.now(UTC),
        llm_model=llm_model,
        llm_prompt_version=PROMPT_VERSION,
        tipo=tipo,
        relevancia=rel_int,
        severity_tier=map_relevancia_to_tier(rel_int),
        resumo=resumo[: limits.MAX_SUMMARY_LENGTH],
        metadados_extraidos=metadados,
        tags=tags,
        topics=topics,
    )


async def classify_with_provider(
    items: Sequence[RawItem],
    provider: LLMProvider,
    *,
    llm_model: str,
) -> list[LLMResult]:
    """Classifica batch de items via provider, com retry e validação.

    Args:
        items: até `MAX_BATCH_LLM` items para classificar de uma vez.
        provider: implementação de `LLMProvider`.
        llm_model: identificação do modelo (registrado em LLMResult).

    Returns:
        Lista de `LLMResult` na mesma ordem dos items.

    Raises:
        ValueError: se response não pôde ser validado mesmo após retries.
    """
    if not items:
        return []
    if len(items) > limits.MAX_BATCH_LLM:
        msg = f"Batch excede MAX_BATCH_LLM ({limits.MAX_BATCH_LLM})"
        raise ValueError(msg)

    items_text = [build_item_text(it) for it in items]

    retryer = AsyncRetrying(
        stop=stop_after_attempt(limits.RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        retry=retry_if_exception_type((ValidationError, ValueError, json.JSONDecodeError)),
        reraise=True,
    )

    async for attempt in retryer:
        with attempt:
            raw_responses = await provider.classify_batch(items_text)
            if len(raw_responses) != len(items):
                msg = f"Provider retornou {len(raw_responses)} respostas para {len(items)} items"
                raise ValueError(msg)

            results: list[LLMResult] = []
            for raw in raw_responses:
                if not isinstance(raw, dict):
                    msg = f"Resposta não-dict do LLM: {type(raw).__name__}"
                    raise ValueError(msg)
                results.append(parse_llm_response(raw, llm_model=llm_model))

            logger.info(
                "llm.batch_classified",
                count=len(results),
                model=llm_model,
                prompt_version=PROMPT_VERSION,
            )
            return results

    msg = "Classificação falhou após retries"  # pragma: no cover
    raise ValueError(msg)  # pragma: no cover
