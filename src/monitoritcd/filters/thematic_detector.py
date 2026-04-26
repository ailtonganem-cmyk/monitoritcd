"""Detector temático — extrai sinais estruturados de textos jurídicos PT-BR.

Cobre 22 itens da Categoria 2 do IDEAS.md (Processamento & Classificação).
Cada função recebe `text: str` e retorna um booleano (presença/ausência) ou
um valor estruturado (ex: lista de números de Tema STF/STJ).

Alimenta `LLMResult.metadados_extraidos` no pipeline pós-coleta. Roda
**antes** do LLM (heurístico, zero custo) — o LLM continua extraindo
campos que exigem compreensão profunda, mas estes sinais já vêm prontos.

Princípio canônico aplicado:
- Princípio 1 (não confiar no frontend): texto recebido vem do `RawItem`,
  já validado por pydantic. Defesa adicional: `unicodedata.normalize("NFKC")`
  e bound em tamanho via texto do RawItem.

Idioma: regexes PT-BR. Inglês não é alvo (sistema é tributário brasileiro).

Itens IDEAS.md cobertos:
- #54 — extrair número de ato (delegado a `_extract_numero_ato` em dedup.py)
- #59 — mudança de alíquota (regex %)
- #61 — sanção vs veto
- #62 — relator de PL/decisão
- #66 — revogação (`"revoga a Lei X"`)
- #74 — embargos / RE / REsp
- #75 — recurso repetitivo
- #76 — Tema STF/STJ
- #77 — cross-reference de normas citadas
- #78 — valores monetários
- #79-#84, #91-#95 — temas específicos do domínio (ITCD, sucessões, regime de bens)
- #87 — modulação de efeitos
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable as _Callable
else:
    from collections.abc import Callable as _Callable  # noqa: TC003

# ─────────────────────────────────────────────────────────────────────────────
# Patterns
# ─────────────────────────────────────────────────────────────────────────────

# #54 — Número de ato (mesmo padrão de dedup, exposto aqui também).
# Aceita "Lei 14.123/2024" (ponto de milhar) ou "Lei 1234/2024".
RE_NUMERO_ATO: Final[re.Pattern[str]] = re.compile(
    r"(?:lei|decreto|portaria|resolu\w+|instru\w+|in)\s*(?:complementar\s*)?"
    r"(?:n[ºo°.\s]+|n[uú]m\.?\s*|n[uú]mero\s*)?"
    r"(\d{1,3}(?:\.\d{3})*|\d{1,5})[/.](\d{4})",
    re.IGNORECASE,
)

# #59 — Alíquota: percentuais simples ou progressivos
RE_ALIQUOTA: Final[re.Pattern[str]] = re.compile(
    r"\b(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s*"
    r"(?:de\s+(?:itcd|itcmd|itd|imposto)|sobre|para|incidente)",
    re.IGNORECASE,
)
RE_ALIQUOTA_RANGE: Final[re.Pattern[str]] = re.compile(
    r"\b(\d{1,2}(?:[.,]\d)?)\s*%\s*(?:a|até|-)\s*(\d{1,2}(?:[.,]\d)?)\s*%",
    re.IGNORECASE,
)

# #61 — Sanção vs veto presidencial/governamental
RE_SANCAO: Final[re.Pattern[str]] = re.compile(
    r"\b(?:sanciona(?:da|do|r|ção)?|sancion(?:a|ou))\b",
    re.IGNORECASE,
)
RE_VETO: Final[re.Pattern[str]] = re.compile(
    r"\b(?:vet(?:a|ou|ado|ada|o\b|ar)|veto\s+(?:parcial|total))\b",
    re.IGNORECASE,
)

# #62 — Relator (parlamentar ou magistrado).
# Formatos aceitos: "Relator: <Nome>", "Relator <Nome>", "Relator Min. <Nome>".
# Captura 2-5 palavras com inicial maiúscula após título opcional.
RE_RELATOR: Final[re.Pattern[str]] = re.compile(
    r"relator[ai]?\s*[:\s][\s\.]*"
    r"(?:dep\.?|sen\.?|min(?:istro)?\.?|des(?:embargador)?\.?|"
    r"juiz|ju[ií]za|prof\.?)?\s*\.?\s*"
    r"([A-Z][a-zà-ú]+(?:\s+(?:da|de|do|das|dos|e)\s+[A-Z][a-zà-ú]+|\s+[A-Z][a-zà-ú]+){1,4})",
    re.IGNORECASE,
)

# #66 — Revogação (item Tier 2 da triagem).
# "revoga", "revogam", "revogam-se", "revoga-se a Lei X", "revogadas as Leis X e Y".
RE_REVOGACAO: Final[re.Pattern[str]] = re.compile(
    r"revog\w+(?:\s*-?\s*se)?\s+"
    r"(?:a|o|as|os|se|aos?\s+termos\s+d[aoe]s?)?\s*"
    r"(?:lei|decreto|portaria|resolu\w+|instru\w+|art(?:igo)?|inciso|par[áa]grafo)?\s*"
    r"(?:complementar\s*)?(?:n[ºo°.]?\s*)?(\d{1,5}(?:[/.]\d{4})?)",
    re.IGNORECASE,
)

# #74 — Recursos: embargos infringentes, recurso especial (REsp), recurso extraordinário (RE)
RE_EMBARGOS: Final[re.Pattern[str]] = re.compile(
    r"\bembargos?\s+(?:infringentes?|de\s+divergência|declaração)\b",
    re.IGNORECASE,
)
RE_RESP: Final[re.Pattern[str]] = re.compile(
    r"\b(?:recurso\s+especial|REsp|R\.\s*Esp\.)\b(?:\s*nº?\s*\d{1,7})?",
    re.IGNORECASE,
)
RE_RE_RECURSO: Final[re.Pattern[str]] = re.compile(
    r"\b(?:recurso\s+extraordinário|^RE\s+\d|R\.\s*E\.)\b",
    re.IGNORECASE,
)

# #75 — Recurso repetitivo
RE_REPETITIVO: Final[re.Pattern[str]] = re.compile(
    r"\b(?:rito\s+dos?\s+|recurso(?:s)?\s+|matéria\s+)?repetitiv[ao]s?\b",
    re.IGNORECASE,
)

# #76 — Tema STF/STJ. Pega "Tema 825", "Tema STF nº 825", "Tema de
# repercussão geral 100", etc. Match permissivo: aceita até 30 chars
# não-numéricos entre "Tema" e o número.
RE_TEMA: Final[re.Pattern[str]] = re.compile(
    r"\bTema\b[^\d\n]{0,40}?(\d{1,4})",
    re.IGNORECASE,
)

# #77 — Cross-reference: normas citadas (Lei nº X/Y, art. Z, súmulas).
# Aceita ponto de milhar no número. Captura número/ano (ano obrigatório
# para distinguir de citações de artigo isolado).
RE_NORMA_CITADA: Final[re.Pattern[str]] = re.compile(
    r"\b(?:lei|decreto|portaria|resolu\w+|instru\w+|art(?:igo)?|s[uú]mula)"
    r"\s*(?:complementar\s*)?(?:n[ºo°.]?\s*)?"
    r"(\d{1,3}(?:\.\d{3})+[/.]\d{4}|\d{1,5}[/.]\d{4})",
    re.IGNORECASE,
)

# #78 — Valores monetários (R$ X, R$ X.XXX,YY, milhão/bilhão)
RE_VALOR_MONETARIO: Final[re.Pattern[str]] = re.compile(
    r"R\$\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?(?:\s*(?:mil|milhão|milhões|bilhão|bilhões))?",
    re.IGNORECASE,
)

# #79-#84, #91-#95 — temas específicos
TEMAS_ESPECIFICOS: Final[dict[str, tuple[str, ...]]] = {
    "planejamento_sucessorio": (r"planejamento\s+sucessório",),
    "holding_familiar": (
        r"holding\s+familiar",
        r"holding\s+patrimonial",
    ),
    "doacao_com_usufruto": (
        r"doação\s+com\s+reserva\s+de\s+usufruto",
        r"reserva\s+de\s+usufruto",
        r"usufruto\s+vitalício",
    ),
    "testamento": (
        r"\btestamento\b",
        r"\btestador(?:a)?\b",
        r"disposição\s+de\s+última\s+vontade",
    ),
    "offshore_exterior": (
        r"\boffshore\b",
        r"bens\s+(?:no\s+)?(?:exterior|estrangeiros?)",
        r"sucessão\s+(?:internacional|transnacional)",
        r"trust\s+(?:familiar|sucessório)?",
    ),
    "aliquota_progressiva": (
        r"alíquota\s+progressiva",
        r"progressividade\s+(?:da\s+)?alíquota",
        r"tabela\s+progressiva",
    ),
    "pec_itcd_federal": (
        r"PEC\s+\d+\s*[/.]\s*\d+(?:[\s\S]{0,200}ITCD|ITCMD)",
        r"unificação\s+(?:nacional\s+)?do\s+ITCD",
        r"ITCD\s+federal",
        r"reforma\s+tributária[\s\S]{0,150}(?:ITCD|herança|sucessão)",
    ),
    "fato_gerador": (
        r"fato\s+gerador\s+(?:do\s+)?(?:ITCD|ITCMD|imposto)",
        r"\bfato\s+gerador\b",
    ),
    "base_de_calculo": (
        r"base\s+de\s+cálculo",
        r"valor\s+venal\s+(?:de\s+referência|do\s+bem|tributável)",
    ),
    "isencao": (
        r"\bisenção\b",
        r"\bisento\b",
        r"\bisentar\b",
    ),
    "imunidade": (
        r"\bimunidade\s+tributária\b",
        r"imunidade\s+(?:recíproca|de\s+templos|cultural)",
    ),
    "gia_itcmd": (
        r"\bGIA[-\s]?ITCMD\b",
        r"\bGIA\b",
        r"declaração\s+(?:de\s+)?ITCMD",
        r"obrigação\s+acessória",
    ),
}

# Compilar uma vez (otimização)
_TEMAS_COMPILADOS: Final[dict[str, list[re.Pattern[str]]]] = {
    nome: [re.compile(p, re.IGNORECASE) for p in patterns]
    for nome, patterns in TEMAS_ESPECIFICOS.items()
}

# #87 — Modulação de efeitos
RE_MODULACAO: Final[re.Pattern[str]] = re.compile(
    r"modulação\s+(?:de\s+|dos\s+)?efeitos",
    re.IGNORECASE,
)

# Limite defensivo (Princípio 2 — input_limits)
MAX_TEXT_BYTES: Final[int] = 1_000_000  # 1 MB; texto raw já tem MAX no RawItem


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Normaliza texto para detecção (NFKC, sem caracteres de controle)."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(c for c in text if c.isprintable() or c.isspace())


def _bounded(text: str | None) -> str:
    """Retorna texto truncado defensivamente (input_limits)."""
    if not text:
        return ""
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        text = text[: MAX_TEXT_BYTES // 2]
    return _normalize(text)


# ─────────────────────────────────────────────────────────────────────────────
# Detectores individuais (cada um cobre 1 item do IDEAS.md)
# ─────────────────────────────────────────────────────────────────────────────


def detect_numero_ato(text: str | None) -> str | None:
    """#54 — Extrai número/ano do ato (Lei 1234/2026, Decreto nº 5/2024, etc.).

    Normaliza removendo ponto de milhar (Lei 14.123/2024 → '14123/2024').
    """
    text = _bounded(text)
    m = RE_NUMERO_ATO.search(text)
    if m:
        numero = m.group(1).replace(".", "")
        return f"{numero}/{m.group(2)}"
    return None


def detect_aliquotas(text: str | None) -> list[str]:
    """#59 — Lista alíquotas mencionadas (ex: ['4%', '8%'])."""
    text = _bounded(text)
    direct = RE_ALIQUOTA.findall(text)
    found = [f"{p.replace(',', '.')}%" for p in direct]
    for low, high in RE_ALIQUOTA_RANGE.findall(text):
        found.append(f"{low.replace(',', '.')}%-{high.replace(',', '.')}%")
    return found


def detect_sancao(text: str | None) -> bool:
    """#61 — True se texto menciona sanção (governador/presidente)."""
    return bool(RE_SANCAO.search(_bounded(text)))


def detect_veto(text: str | None) -> bool:
    """#61 — True se texto menciona veto."""
    return bool(RE_VETO.search(_bounded(text)))


def detect_relator(text: str | None) -> str | None:
    """#62 — Nome do relator (PL ou jurisprudência), se identificável."""
    text = _bounded(text)
    m = RE_RELATOR.search(text)
    if m:
        return m.group(1).strip()
    return None


def detect_revogacao(text: str | None) -> list[str]:
    """#66 — Lista normas revogadas mencionadas (ex: ['1234/2020']).

    Para casos como "Revogam-se a Lei 100/2010 e a Lei 200/2015", varre 200
    chars após o gatilho `revoga*` e captura todas as normas (Lei XXX/AAAA)
    nesse trecho.
    """
    text = _bounded(text)
    normas: list[str] = []
    for trigger in re.finditer(r"\brevog\w+", text, re.IGNORECASE):
        # Janela de 200 chars após o gatilho
        end = min(trigger.end() + 200, len(text))
        trecho = text[trigger.end() : end]
        for m in RE_NORMA_CITADA.finditer(trecho):
            normas.append(m.group(1))
    # Dedup mantendo ordem
    seen: list[str] = []
    for n in normas:
        if n not in seen:
            seen.append(n)
    return seen


def detect_recurso_tipo(text: str | None) -> set[str]:
    """#74 — Set de tipos de recurso identificados ('embargos','resp','re')."""
    text = _bounded(text)
    tipos: set[str] = set()
    if RE_EMBARGOS.search(text):
        tipos.add("embargos")
    if RE_RESP.search(text):
        tipos.add("resp")
    if RE_RE_RECURSO.search(text):
        tipos.add("re")
    return tipos


def detect_repetitivo(text: str | None) -> bool:
    """#75 — True se texto menciona rito/recurso repetitivo."""
    return bool(RE_REPETITIVO.search(_bounded(text)))


def detect_temas_stf_stj(text: str | None) -> list[str]:
    """#76 — Lista números de Tema STF/STJ mencionados."""
    text = _bounded(text)
    return RE_TEMA.findall(text)


def detect_normas_citadas(text: str | None, limit: int = 20) -> list[str]:
    """#77 — Lista normas citadas (cross-reference) — dedup, capada em `limit`."""
    text = _bounded(text)
    seen: list[str] = []
    for m in RE_NORMA_CITADA.findall(text):
        if m and m not in seen:
            seen.append(m)
            if len(seen) >= limit:
                break
    return seen


def detect_valores_monetarios(text: str | None, limit: int = 10) -> list[str]:
    """#78 — Lista valores monetários encontrados (capada em `limit`)."""
    text = _bounded(text)
    matches = RE_VALOR_MONETARIO.findall(text)
    return matches[:limit]


def detect_modulacao_efeitos(text: str | None) -> bool:
    """#87 — True se texto menciona modulação de efeitos."""
    return bool(RE_MODULACAO.search(_bounded(text)))


def detect_temas_especificos(text: str | None) -> set[str]:
    """#79-#84, #91-#95 — Set com nomes dos temas específicos detectados.

    Returns:
        Set de chaves de TEMAS_ESPECIFICOS encontradas no texto.
    """
    text = _bounded(text)
    if not text:
        return set()

    found: set[str] = set()
    for tema, patterns in _TEMAS_COMPILADOS.items():
        for pat in patterns:
            if pat.search(text):
                found.add(tema)
                break
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Detector consolidado — output estruturado para metadados_extraidos
# ─────────────────────────────────────────────────────────────────────────────


def _collect_value_detectors(full: str) -> dict[str, str]:
    """Detectores que retornam string|None ou listas (truthy/falsy)."""
    out: dict[str, str] = {}
    if numero := detect_numero_ato(full):
        out["numero_ato"] = numero
    if aliquotas := detect_aliquotas(full):
        out["aliquotas"] = ",".join(aliquotas[:5])
    if relator := detect_relator(full):
        out["relator"] = relator
    if revogacoes := detect_revogacao(full):
        out["revogacoes_citadas"] = ",".join(revogacoes[:5])
    if tipos := detect_recurso_tipo(full):
        out["recurso_tipos"] = ",".join(sorted(tipos))
    if temas := detect_temas_stf_stj(full):
        out["temas_stf_stj"] = ",".join(temas[:10])
    if normas := detect_normas_citadas(full):
        out["normas_citadas"] = ",".join(normas[:10])
    if valores := detect_valores_monetarios(full):
        out["valores_monetarios"] = ",".join(valores[:5])
    if temas_esp := detect_temas_especificos(full):
        out["temas_especificos"] = ",".join(sorted(temas_esp))
    return out


def _collect_boolean_detectors(full: str) -> dict[str, str]:
    """Detectores que retornam bool (mapeados para 'true' se presente)."""
    bool_detectors: tuple[tuple[str, _Callable[[str], bool]], ...] = (
        ("sancao_detectada", detect_sancao),
        ("veto_detectado", detect_veto),
        ("repetitivo", detect_repetitivo),
        ("modulacao_efeitos", detect_modulacao_efeitos),
    )
    return {key: "true" for key, fn in bool_detectors if fn(full)}


def detect_all(titulo: str | None, texto: str | None) -> dict[str, str]:
    """Roda todos os detectores e retorna dict serializável (str → str).

    Saída encaixa em `LLMResult.metadados_extraidos` (dict[str, str] com
    `MAX_METADATA_FIELDS` validado pelo pydantic).
    """
    full = " ".join([titulo or "", texto or ""])
    return {
        **_collect_value_detectors(full),
        **_collect_boolean_detectors(full),
    }


__all__ = [
    "detect_aliquotas",
    "detect_all",
    "detect_modulacao_efeitos",
    "detect_normas_citadas",
    "detect_numero_ato",
    "detect_recurso_tipo",
    "detect_relator",
    "detect_repetitivo",
    "detect_revogacao",
    "detect_sancao",
    "detect_temas_especificos",
    "detect_temas_stf_stj",
    "detect_valores_monetarios",
    "detect_veto",
]
