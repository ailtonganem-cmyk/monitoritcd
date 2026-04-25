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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    CUSTOM = "custom"


class Topic(StrEnum):
    """Divisão temática do sistema.

    Permite cobrir áreas correlatas a ITCD sem misturar conceitos:
    - ITCD: tributário (alíquotas, fato gerador, IN, portarias).
    - SUCESSOES: Direito Civil — herança, testamento, inventário, partilha (CC 1.784+).
    - REGIME_BENS: regimes matrimoniais (CC 1.639-1.688) — afeta o que se transmite.
    """

    ITCD = "itcd"
    SUCESSOES = "sucessoes"
    REGIME_BENS = "regime_bens"


# ─────────────────────────────────────────────────────────────────────────────
# Tipos anotados reutilizáveis (com input_limits)
# ─────────────────────────────────────────────────────────────────────────────

OwnerId = Annotated[str, Field(min_length=1, max_length=limits.MAX_OWNER_ID_LENGTH)]
SourceId = Annotated[str, Field(min_length=1, max_length=limits.MAX_SOURCE_ID_LENGTH)]
DocId = Annotated[str, Field(min_length=1, max_length=limits.MAX_DOC_ID_LENGTH)]
UFCode = Annotated[str, Field(pattern=limits.UF_REGEX)]
URLString = Annotated[str, Field(min_length=1, max_length=limits.MAX_URL_LENGTH)]
Title = Annotated[str, Field(min_length=1, max_length=limits.MAX_TITLE_LENGTH)]
Summary = Annotated[str, Field(min_length=1, max_length=limits.MAX_SUMMARY_LENGTH)]
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
    geo_restricted: bool = False
    """True quando o servidor da fonte rejeita conexões de IPs fora do BR.

    Fontes com `geo_restricted=True` são puladas em GitHub Actions runners (US)
    e devem ser coletadas via worker local em Windows Task Scheduler.
    Ver `scripts/install_local_monitor_task.ps1`.
    """
    notas: str | None = Field(default=None, max_length=1000)
    topics: list[Topic] = Field(default_factory=lambda: [Topic.ITCD], max_length=10)

    @field_validator("selectors")
    @classmethod
    def _selectors_size(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is not None and len(v) > limits.MAX_METADATA_FIELDS:
            msg = f"selectors excede MAX_METADATA_FIELDS ({limits.MAX_METADATA_FIELDS})"
            raise ValueError(msg)
        return v


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
    metadados_extraidos: dict[
        Annotated[str, Field(max_length=64)],
        Annotated[str, Field(max_length=500)],
    ] = Field(default_factory=dict)
    tags: Annotated[list[Tag], Field(default_factory=list, max_length=limits.MAX_TAGS_PER_DOC)]
    topics: list[Topic] = Field(default_factory=lambda: [Topic.ITCD], max_length=10)

    @field_validator("metadados_extraidos")
    @classmethod
    def _metadata_size(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > limits.MAX_METADATA_FIELDS:
            msg = f"metadados_extraidos excede MAX_METADATA_FIELDS ({limits.MAX_METADATA_FIELDS})"
            raise ValueError(msg)
        return v


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

    schema_version: int = Field(ge=1, default=1)
    doc_id: DocId
    source: Source
    original: RawItem
    llm: LLMResult | None = None
    notificacao: NotificacaoStatus = Field(default_factory=NotificacaoStatus)
    status: StatusDocumento = StatusDocumento.PENDING
    cluster_id: str | None = Field(default=None, max_length=128)


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
    "ActiveStatesConfig",
    "AuditLogEntry",
    "BotCommand",
    "Documento",
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
    "Watch",
]
