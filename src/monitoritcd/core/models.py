"""Modelos pydantic do domínio.

Validação no boundary HTTP→modelo (Princípio Canônico 1: nunca confiar no frontend).
Todo input passa por aqui antes de qualquer lógica de negócio.

Schema separa estritamente:
- `original/`: write-once, fonte da verdade, preservado verbatim.
- `llm/`: gerado por LLM, reprocessável.
- `notificacao/`: estado de notificação.

Princípios canônicos aplicados:
1. `extra="forbid"` em todo modelo — não aceita campos não declarados.
2. `Field(max_length=...)` em todo string — input_limits obrigatórios.
3. `OwnerScoped` força owner_id em todo doc raiz — defense-in-depth.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — pydantic precisa em runtime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from monitoritcd.core import limits

# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class TipoAto(StrEnum):
    """Tipo do ato classificado pelo LLM."""

    PROJETO_LEI = "projeto_lei"
    LEI_SANCIONADA = "lei_sancionada"
    DECRETO = "decreto"
    INSTRUCAO_NORMATIVA = "instrucao_normativa"
    PORTARIA = "portaria"
    NOTICIA = "noticia"
    JURISPRUDENCIA = "jurisprudencia"
    DOUTRINA = "doutrina"
    OUTRO = "outro"


class SeverityTier(StrEnum):
    """Tier de severidade — controla canal e urgência da notificação."""

    CRITICO = "critico"  # push imediato (Telegram)
    ALTA = "alta"  # digest do dia, em destaque
    NORMAL = "normal"  # digest do dia
    BAIXA = "baixa"  # digest semanal
    DESCARTADO = "descartado"  # não notifica


class StatusDocumento(StrEnum):
    """Estado do documento no pipeline."""

    PENDING = "pending"
    CLASSIFIED = "classified"
    NOTIFIED = "notified"
    ARCHIVED = "archived"


class TipoFonte(StrEnum):
    """Categoria da fonte coletada."""

    ASSEMBLEIA = "assembleia"
    SEFAZ = "sefaz"
    DOE = "doe"
    JURISPRUDENCIA = "jurisprudencia"
    NOTICIA = "noticia"
    DOUTRINA = "doutrina"


class Parser(StrEnum):
    """Parser usado pelo coletor."""

    GENERIC_RSS = "generic_rss"
    GENERIC_HTML = "generic_html"
    LEXML = "lexml"
    LEXML_PORTAL = "lexml_portal"
    ALMG = "almg"
    ALEP = "alep"
    ALEPE = "alepe"
    SAPL = "sapl"
    CAMARA_DEPUTADOS = "camara_deputados"
    SENADO = "senado"
    SEFAZ_SP = "sefaz_sp"
    ALESP = "alesp"
    IOF_MG = "iof_mg"
    CUSTOM = "custom"


class Topic(StrEnum):
    """Divisão temática default do sistema.

    Permite cobrir áreas correlatas a ITCD sem misturar conceitos:
    - ITCD: tributário (alíquotas, fato gerador, IN, portarias).
    - SUCESSOES: Direito Civil — herança, testamento, inventário, partilha (CC 1.784+).
    - REGIME_BENS: regimes matrimoniais (CC 1.639-1.688) — afeta o que se transmite.

    Topics extras podem ser adicionados em runtime via /topicos (ExtraTopicsConfig),
    e ficam armazenados em LLMResult.topics como strings livres validadas por regex.
    """

    ITCD = "itcd"
    SUCESSOES = "sucessoes"
    REGIME_BENS = "regime_bens"


# Conjunto imutável de IDs default — útil para validação anti-colisão em /topicos.
DEFAULT_TOPIC_IDS: frozenset[str] = frozenset(t.value for t in Topic)


# ─────────────────────────────────────────────────────────────────────────────
# Tipos anotados reutilizáveis (com input_limits)
# ─────────────────────────────────────────────────────────────────────────────

OwnerId = Annotated[str, Field(min_length=1, max_length=limits.MAX_OWNER_ID_LENGTH)]
TopicId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=limits.MAX_TOPIC_ID_LENGTH,
        pattern=r"^[a-z][a-z0-9_]{0,31}$",
    ),
]
SourceId = Annotated[str, Field(min_length=1, max_length=limits.MAX_SOURCE_ID_LENGTH)]
DocId = Annotated[str, Field(min_length=1, max_length=limits.MAX_DOC_ID_LENGTH)]
UFCode = Annotated[str, Field(pattern=limits.UF_REGEX)]
URLString = Annotated[str, Field(min_length=1, max_length=limits.MAX_URL_LENGTH)]
Title = Annotated[str, Field(min_length=1, max_length=limits.MAX_TITLE_LENGTH)]
Summary = Annotated[str, Field(min_length=1, max_length=limits.MAX_SUMMARY_LENGTH)]
FullSummary = Annotated[str, Field(max_length=limits.MAX_FULL_SUMMARY_LENGTH)]
KeyPoint = Annotated[str, Field(min_length=1, max_length=limits.MAX_KEY_POINT_LENGTH)]
SearchText = Annotated[str, Field(max_length=limits.MAX_SEARCH_TEXT_LENGTH)]
SearchTerm = Annotated[str, Field(min_length=1, max_length=limits.MAX_SEARCH_TERM_LENGTH)]
Tag = Annotated[str, Field(min_length=1, max_length=limits.MAX_TAG_LENGTH)]
Relevancia = Annotated[int, Field(ge=limits.RELEVANCIA_MIN, le=limits.RELEVANCIA_MAX)]


# ─────────────────────────────────────────────────────────────────────────────
# Mixins
# ─────────────────────────────────────────────────────────────────────────────


class StrictModel(BaseModel):
    """Base model: forbid extra fields, frozen por default opcional."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OwnerScoped(StrictModel):
    """Mixin para modelos que precisam validar owner_id (defense-in-depth).

    Mesmo single-user, todo doc raiz no Firestore tem owner_id.
    Helper `assert_owner` (em storage) compara com OWNER_ID do env antes de qualquer mutation.
    """

    owner_id: OwnerId


# ─────────────────────────────────────────────────────────────────────────────
# Configuração de fonte (carregada de YAML em sources/)
# ─────────────────────────────────────────────────────────────────────────────


class Source(StrictModel):
    """Configuração declarativa de uma fonte coletada."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SourceId
    uf: UFCode
    nome: Annotated[str, Field(min_length=1, max_length=limits.MAX_SOURCE_NAME_LENGTH)]
    tipo: TipoFonte
    parser: Parser
    url: URLString
    keywords_required: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=100)]],
        Field(default_factory=list, max_length=limits.MAX_KEYWORDS_LIST),
    ]
    selectors: dict[str, str] | None = None
    ativo: bool = True
    fragile: bool = False
    trusted: bool = False
    # True quando o servidor da fonte rejeita conexões de IPs fora do BR.
    # Fontes com `geo_restricted=True` são puladas em GitHub Actions runners (US)
    # e devem ser coletadas via worker local em Windows Task Scheduler.
    # Ver `scripts/install_local_monitor_task.ps1`.
    geo_restricted: bool = False

    # Quando True, o orquestrador pula o Filtro 1 (matches_keywords) para esta
    # fonte. Pareado OBRIGATORIAMENTE com `org_mentions`: aceita items cujo texto
    # contém qualquer string em org_mentions, mesmo sem keyword temática.
    # Caso de uso: monitorar TUDO emitido por ou dirigido a um órgão (ex: SEFAZ-MG
    # no IOF/MG), independente de relacionar a ITCD/sucessões/regime_bens.
    # Combinar `keywords_bypass=True` sem `org_mentions` é rejeitado pelo
    # validador `_bypass_requires_org_mentions`: defesa em camadas, sem trapdoor.
    keywords_bypass: bool = False

    # Variações do nome de um órgão a buscar no texto coletado (normalização
    # NFKC + lower aplicada na comparação, padrão `filters/keywords._normalize`).
    # Exemplo SEFAZ-MG no IOF/MG: ["Secretaria de Estado de Fazenda", "SEFAZ",
    # "SEF/MG", "SEF-MG"]. Item entra se contém qualquer uma das strings.
    # None/lista vazia = sem filtro de órgão. Limite de 10 entradas: nomes de
    # órgãos têm variações finitas; lista inchada é red flag de design.
    org_mentions: (
        list[
            Annotated[
                str,
                Field(
                    min_length=limits.MIN_ORG_MENTION_LENGTH,
                    max_length=limits.MAX_ORG_MENTION_LENGTH,
                ),
            ]
        ]
        | None
    ) = Field(default=None, max_length=limits.MAX_ORG_MENTIONS)

    notas: str | None = Field(default=None, max_length=1000)
    topics: list[TopicId] = Field(default_factory=lambda: [Topic.ITCD.value], max_length=10)

    @field_validator("selectors")
    @classmethod
    def _selectors_size(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is not None and len(v) > limits.MAX_METADATA_FIELDS:
            msg = f"selectors excede MAX_METADATA_FIELDS ({limits.MAX_METADATA_FIELDS})"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _bypass_requires_org_mentions(self) -> Source:
        """Princípio Canônico 1 + 2: defesa em camadas, sem trapdoor implícito.

        keywords_bypass=True remove o Filtro 1 (keywords). Para evitar que isso
        vire 'aceite tudo dessa fonte', exigimos que a fonte declare explicitamente
        QUE órgão está monitorando via org_mentions. Falha = erro de configuração
        do YAML, não de runtime — pega na carga do arquivo.
        """
        if self.keywords_bypass and not self.org_mentions:
            msg = (
                f"Source {self.id!r}: keywords_bypass=True exige org_mentions com "
                "pelo menos 1 entrada (filtro positivo de menção a órgão)"
            )
            raise ValueError(msg)
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Item bruto coletado (antes de filtro/classifier) — IMUTÁVEL
# ─────────────────────────────────────────────────────────────────────────────


class RawItem(StrictModel):
    """Item bruto coletado de uma fonte. Preservado verbatim — write-once.

    LLM **NÃO PODE** modificar este modelo. Apenas lê.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: SourceId
    titulo_raw: Title
    url: URLString
    texto_raw: str | None = Field(default=None, max_length=limits.MAX_RAW_TEXT_LENGTH)
    data_publicacao: datetime | None = None
    fetched_at: datetime
    raw_storage_path: str | None = Field(default=None, max_length=limits.MAX_STORAGE_PATH_LENGTH)
    content_hash: Annotated[str, Field(min_length=64, max_length=64)]  # sha256 hex


# ─────────────────────────────────────────────────────────────────────────────
# Resultado da classificação LLM
# ─────────────────────────────────────────────────────────────────────────────


class LLMResult(StrictModel):
    """Saída do classifier LLM. Reprocessável (ao contrário de RawItem)."""

    classified_at: datetime
    llm_model: Annotated[str, Field(max_length=limits.MAX_LLM_MODEL_NAME_LENGTH)]
    llm_prompt_version: Annotated[str, Field(max_length=limits.MAX_LLM_PROMPT_VERSION_LENGTH)]
    tipo: TipoAto
    relevancia: Relevancia
    severity_tier: SeverityTier
    resumo: Summary
    resumo_completo: FullSummary = ""
    pontos_chave: Annotated[
        list[KeyPoint], Field(default_factory=list, max_length=limits.MAX_KEY_POINTS)
    ]
    motivo_relevancia: Annotated[
        str,
        Field(default="", max_length=limits.MAX_RELEVANCE_REASON_LENGTH),
    ]
    contexto: Annotated[str, Field(default="", max_length=limits.MAX_CONTEXTO_LENGTH)]
    """Contextualização jurídica gerada por IA (Seção 5 do CLAUDE.md).

    Único campo em que o LLM pode usar conhecimento jurídico geral além do
    texto coletado — explica a norma/decisão citada, o que ela muda e o
    significado prático. Sempre apresentado ao dono como gerado por IA.
    """
    assuntos_relacionados: Annotated[
        list[Tag],
        Field(default_factory=list, max_length=limits.MAX_RELATED_SUBJECTS),
    ]
    metadados_extraidos: dict[
        Annotated[str, Field(max_length=64)],
        Annotated[str, Field(max_length=500)],
    ] = Field(default_factory=dict)
    tags: Annotated[list[Tag], Field(default_factory=list, max_length=limits.MAX_TAGS_PER_DOC)]
    topics: list[TopicId] = Field(default_factory=lambda: [Topic.ITCD.value], max_length=10)

    @field_validator("metadados_extraidos")
    @classmethod
    def _metadata_size(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > limits.MAX_METADATA_FIELDS:
            msg = f"metadados_extraidos excede MAX_METADATA_FIELDS ({limits.MAX_METADATA_FIELDS})"
            raise ValueError(msg)
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Índice de busca derivado — armazenado junto ao documento Firestore
# ─────────────────────────────────────────────────────────────────────────────


class DocumentSearchIndex(StrictModel):
    """Corpus pesquisável derivado de `original` + `llm`.

    É materializado no Firestore para tornar o documento útil como base de
    pesquisa futura. Não substitui `original` e pode ser refeito a qualquer
    momento a partir dos campos canônicos.
    """

    index_version: int = Field(ge=1, default=2)
    generated_at: datetime
    text: SearchText = ""
    terms: Annotated[
        list[SearchTerm],
        Field(default_factory=list, max_length=limits.MAX_SEARCH_TERMS),
    ]
    topics: list[TopicId] = Field(default_factory=list, max_length=10)
    prompt_version: Annotated[
        str,
        Field(default="", max_length=limits.MAX_LLM_PROMPT_VERSION_LENGTH),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Estado de notificação
# ─────────────────────────────────────────────────────────────────────────────


class NotificacaoStatus(StrictModel):
    """Estado de notificação do documento."""

    enviada: bool = False
    enviada_em: datetime | None = None
    canais: list[Literal["email", "telegram", "discord", "ntfy"]] = Field(
        default_factory=list,
        max_length=limits.MAX_NOTIFICATION_CHANNELS,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Documento completo (raiz no Firestore) — OwnerScoped
# ─────────────────────────────────────────────────────────────────────────────


class Documento(OwnerScoped):
    """Documento completo armazenado no Firestore.

    Estrutura segue Seção 5 do CLAUDE.md.
    Schema versionado para migrações futuras.
    """

    schema_version: int = Field(ge=1, default=2)
    doc_id: DocId
    source: Source
    original: RawItem
    llm: LLMResult | None = None
    notificacao: NotificacaoStatus = Field(default_factory=NotificacaoStatus)
    status: StatusDocumento = StatusDocumento.PENDING
    cluster_id: str | None = Field(default=None, max_length=128)
    search_index: DocumentSearchIndex | None = None
    user_tags: Annotated[
        list[Tag],
        Field(default_factory=list, max_length=limits.MAX_TAGS_PER_DOC),
    ]
    """Tags atribuidas pelo dono via `/marcar` (separado de `llm.tags`).

    Diferente de `llm.tags` (frozen, write-once via update_llm), este campo
    pode crescer ao longo do tempo conforme o dono marca documentos.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Configuração de UFs ativas (Firestore: config/active_states)
# ─────────────────────────────────────────────────────────────────────────────


class ActiveStatesConfig(OwnerScoped):
    """UFs ativas e silenciamentos. Doc único em Firestore."""

    schema_version: int = Field(ge=1, default=1)
    active_uf: Annotated[
        list[UFCode],
        Field(default_factory=list, max_length=limits.MAX_ACTIVE_UFS),
    ]
    federal_active: bool = True
    silenced_until: dict[UFCode, datetime] = Field(default_factory=dict)
    updated_at: datetime
    updated_by: Annotated[str, Field(max_length=64)]


# ─────────────────────────────────────────────────────────────────────────────
# Configuração de keywords extras dinâmicas (Firestore: config/extra_keywords)
# ─────────────────────────────────────────────────────────────────────────────

# Validação de keyword: 3-100 chars, letras/números/espaços/hífens/acentos.
ExtraKeyword = Annotated[
    str,
    Field(
        min_length=limits.MIN_EXTRA_KEYWORD_LENGTH,
        max_length=limits.MAX_EXTRA_KEYWORD_LENGTH,
        pattern=r"^[\w\s\-áéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇàèìòùÀÈÌÒÙ.,/]+$",
    ),
]


class ExtraKeywordsConfig(OwnerScoped):
    """Keywords adicionadas dinamicamente via /temas, agrupadas por topic.

    Mescla com `KEYWORDS_DEFAULT` no filtro 1 do pipeline. Não substitui:
    extras AMPLIAM o universo de termos buscados antes do LLM.

    Chave do dict é o topic id ("itcd", "sucessoes", "regime_bens" ou um
    topic dinâmico criado via /topicos). Topic special "geral" agrega
    keywords sem topico explícito.
    """

    schema_version: int = Field(ge=1, default=1)
    keywords_by_topic: dict[
        Annotated[str, Field(max_length=64, pattern=r"^[a-z][a-z0-9_]{0,63}$")],
        list[ExtraKeyword],
    ] = Field(default_factory=dict)
    updated_at: datetime
    updated_by: Annotated[str, Field(max_length=64)]

    def total_count(self) -> int:
        """Total de keywords extras somando todos os topics."""
        return sum(len(v) for v in self.keywords_by_topic.values())

    def all_keywords(self) -> list[str]:
        """Flatten: união de todas as keywords extras (sem duplicatas)."""
        seen: set[str] = set()
        for kws in self.keywords_by_topic.values():
            seen.update(kws)
        return sorted(seen)


# ─────────────────────────────────────────────────────────────────────────────
# Configuração de topics extras dinâmicos (Firestore: config/extra_topics)
# ─────────────────────────────────────────────────────────────────────────────


class TopicEntry(StrictModel):
    """Topic dinâmico criado pelo dono via /topicos.

    Topic id é o que aparece em LLMResult.topics (string livre validada por regex).
    Descrição alimenta o system prompt do LLM em runtime para que ele saiba quando
    classificar nessa categoria nova.
    """

    id: TopicId
    descricao: Annotated[
        str,
        Field(
            min_length=limits.MIN_TOPIC_DESCRIPTION_LENGTH,
            max_length=limits.MAX_TOPIC_DESCRIPTION_LENGTH,
        ),
    ]
    criado_em: datetime
    criado_por: Annotated[str, Field(max_length=64)]


class ExtraTopicsConfig(OwnerScoped):
    """Topics dinâmicos persistidos em config/extra_topics no Firestore.

    Defaults (itcd, sucessoes, regime_bens) NÃO são duplicados aqui — são
    sempre os 3 do enum Topic. Esta config armazena apenas os EXTRAS criados
    pelo dono via /topicos adicionar.
    """

    schema_version: int = Field(ge=1, default=1)
    topics: list[TopicEntry] = Field(default_factory=list, max_length=limits.MAX_EXTRA_TOPICS)
    updated_at: datetime
    updated_by: Annotated[str, Field(max_length=64)]

    def topic_ids(self) -> set[str]:
        """Conjunto de IDs dos topics extras (não inclui defaults)."""
        return {t.id for t in self.topics}

    def all_topic_ids(self) -> frozenset[str]:
        """Conjunto de IDs válidos: defaults + extras.

        Use no parse do LLMResult para aceitar topic dinâmico que o LLM emitiu.
        """
        return DEFAULT_TOPIC_IDS | self.topic_ids()


# ─────────────────────────────────────────────────────────────────────────────
# Watch list
# ─────────────────────────────────────────────────────────────────────────────


class Watch(OwnerScoped):
    """Item da watch list — alerta prioritário em match."""

    watch_id: Annotated[str, Field(max_length=64)]
    pattern: Annotated[str, Field(min_length=1, max_length=500)]
    pattern_type: Literal["term", "regex", "pl_number", "uf_topic"]
    uf: UFCode | None = None
    relevancia_min: Relevancia = 5
    expires_at: datetime | None = None
    cooldown_hours: int = Field(ge=0, le=168, default=0)  # max 1 semana
    last_triggered: datetime | None = None
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Audit log (append-only, hash-chained)
# ─────────────────────────────────────────────────────────────────────────────


class AuditLogEntry(OwnerScoped):
    """Entry imutável do audit log com hash chain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: Annotated[str, Field(max_length=64)]
    timestamp: datetime
    actor: Annotated[str, Field(max_length=128)]  # "bot:OWNER", "system:cron", etc.
    action: Annotated[str, Field(max_length=128)]  # "states.activate", "doc.notify", ...
    payload_hash: Annotated[str, Field(min_length=64, max_length=64)]  # sha256 do payload
    prev_hash: Annotated[str, Field(min_length=64, max_length=64)]  # hash da entry anterior
    result: Literal["success", "failure"]
    error: str | None = Field(default=None, max_length=500)


# ─────────────────────────────────────────────────────────────────────────────
# Comandos de bot (validação de input — Princípio Canônico 1)
# ─────────────────────────────────────────────────────────────────────────────


class BotCommand(StrictModel):
    """Comando recebido do bot. Validado antes de processar."""

    chat_id: int
    user_id: int
    command: Annotated[str, Field(min_length=1, max_length=limits.MAX_BOT_COMMAND_LENGTH)]
    args: Annotated[
        list[Annotated[str, Field(max_length=limits.MAX_BOT_ARG_LENGTH)]],
        Field(default_factory=list, max_length=10),
    ]
    received_at: datetime


__all__ = [
    "DEFAULT_TOPIC_IDS",
    "ActiveStatesConfig",
    "AuditLogEntry",
    "BotCommand",
    "DocumentSearchIndex",
    "Documento",
    "ExtraKeyword",
    "ExtraKeywordsConfig",
    "ExtraTopicsConfig",
    "FullSummary",
    "KeyPoint",
    "LLMResult",
    "NotificacaoStatus",
    "OwnerScoped",
    "Parser",
    "RawItem",
    "SeverityTier",
    "Source",
    "StatusDocumento",
    "StrictModel",
    "TipoAto",
    "TipoFonte",
    "Topic",
    "TopicEntry",
    "TopicId",
    "Watch",
]
