"""Coletor do Diário Oficial Eletrônico de MG (Jornal Minas Gerais).

Descoberto via reverse engineering em 2026-05-19 (ver
`docs/iof-mg-architecture.md`). O backend é uma API .NET REST em
`https://www.jornalminasgerais.mg.gov.br/api/v1/` que expõe edições
diárias como PDFs assinados digitalmente (PKCS#7 / ICP-Brasil).

Pipeline da coleta:

1. **Auth anônimo**: POST `/Autenticacao/Autenticar` com body `{}` retorna
   JWT efêmero (sub=`usuarioPortal`, exp ~2h). Não é credencial real — é
   um guest token público; não vai pro GitHub Secrets, é obtido em runtime.

2. **Calendário**: GET `/Jornal/ObterUltimaEdicaoECalendarioParaHome`
   retorna IDs dos cadernos da edição mais recente (Executivo / Municípios /
   Terceiros). IDs mudam todo dia.

3. **Metadados + índice**: GET `/Jornal/ObterEdicaoPorId/{idCaderno}` retorna
   `secoes[]` com `(descricao, paginaInicial)` por órgão dentro do caderno.

4. **Download do PDF**: GET `/Caderno/ObterArquivoCadernoPorId?id={idCaderno}`
   com `Authorization: Bearer <JWT>` retorna JSON
   `{dados:{arquivo:"<base64>"}}` onde o base64 envelopa o PKCS#7 SignedData.

5. **Extração**: decode base64 → busca `%PDF-` (start) e `%%EOF` (end) →
   bytes do PDF original (sem validar assinatura nesta versão).

6. **Parse**: `pypdf.PdfReader().pages[i].extract_text()` por página, depois
   regex para fatiar em atos (`DECRETO`, `PORTARIA`, `RESOLUÇÃO`, etc).

7. **Filtro local**: aplica `source.org_mentions` no texto de cada ato
   antes de gerar `RawItem`. Reduz volume de ~500 atos/dia para ~30-50 que
   mencionam o órgão monitorado. Evita gerar items descartáveis.

Princípios canônicos aplicados:
- **MAX_BYTES**: envelope base64 limitado por `MAX_PDF_BYTES * 2` (base64
  expande ~4/3; com folga); PDF extraído limitado a `MAX_PDF_BYTES`.
- **input_limits**: número de atos por execução limitado a `MAX_ACTS_PER_RUN`
  para evitar OOM em edições anormalmente grandes.
- **Defense in depth**: JWT nunca persistido em disco; renovado a cada
  execução; logs filtram tokens via structlog redactor.
- **Original verbatim**: texto do ato preservado exatamente como veio do PDF
  (Princípio Canônico 5 — LLM não modifica original).
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import httpx
import structlog

from monitoritcd.core import limits
from monitoritcd.core.base_collector import BaseCollector, CollectorError
from monitoritcd.filters.keywords import matches_keywords

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

# Base URL hardcoded no collector — não vem de YAML (anti-SSRF: URL é literal).
_API_BASE: Final[str] = "https://www.jornalminasgerais.mg.gov.br/api/v1"
_AUTH_URL: Final[str] = f"{_API_BASE}/Autenticacao/Autenticar"
_HOME_URL: Final[str] = f"{_API_BASE}/Jornal/ObterUltimaEdicaoECalendarioParaHome"
_EDICAO_URL_TPL: Final[str] = f"{_API_BASE}/Jornal/ObterEdicaoPorId/{{id}}"
_PDF_URL_TPL: Final[str] = f"{_API_BASE}/Caderno/ObterArquivoCadernoPorId?id={{id}}"

# Deeplink para citar nos RawItems (clicado abre o caderno no site).
_DEEPLINK_TPL: Final[str] = "https://www.jornalminasgerais.mg.gov.br/edicao-do-dia?dados={dados}"

# Caderno default: "Diário do Executivo". Configurável via selectors.caderno.
_DEFAULT_CADERNO: Final[str] = "Diário do Executivo"

# Limite de atos por execução — guard rail contra edição anormal.
# Edição típica: ~500 atos no Executivo; filtro local reduz pra ~30-50.
# Teto de 2000 cobre dias atípicos sem risco de OOM.
_MAX_ACTS_PER_RUN: Final[int] = 2000

# Tamanho máximo do envelope base64 (PDF de 20 MB → base64 ~27 MB; folga 2x).
_MAX_ENVELOPE_BYTES: Final[int] = limits.MAX_PDF_BYTES * 2

# Tamanho máximo do texto de um único ato. Atos longos (regulamentação
# completa de ICMS por ex.) podem ter dezenas de páginas — truncamos pelo
# limite do `texto_raw` no RawItem (MAX_RAW_TEXT_LENGTH = 1 MB).
_MAX_ACT_TEXT_BYTES: Final[int] = limits.MAX_RAW_TEXT_LENGTH

# Magic bytes do PDF e fim do PDF.
_PDF_MAGIC: Final[bytes] = b"%PDF-"
_PDF_EOF: Final[bytes] = b"%%EOF"

# Tipos de ato — conjunto canônico usado tanto na regex de cabeçalho quanto
# no pré-processamento de quebras (pypdf concatena linhas em alguns layouts).
_ACT_TIPO_ALT: Final[str] = (
    r"DECRETO(?:\s+NE)?"
    r"|PORTARIA(?:\s+\w{1,15})?"
    r"|RESOLU[ÇC][ÃA]O(?:\s+\w{1,15})?"
    r"|INSTRU[ÇC][ÃA]O\s+NORMATIVA"
    r"|EXTRATO(?:\s+DE\s+\w{1,30})?"
    r"|EDITAL(?:\s+DE\s+\w{1,30})?"
)

# Regex de cabeçalhos de atos. Cobre os tipos comuns no IOF/MG (DECRETO,
# PORTARIA, RESOLUÇÃO [com sufixo de órgão], INSTRUÇÃO NORMATIVA, EXTRATO,
# EDITAL). Aceita variações:
#   - "DECRETO NE" (Minas usa esse sufixo p/ Não-Estadual / Não-Executivo)
#   - "DECRETO Nº 123" ou "DECRETO N° 123" ou "DECRETO Nº123"
#   - número pode conter ponto, barra, espaço: "123.456/2026"
# Case-insensitive; flag MULTILINE para ^ casar com início de linha.
_ACT_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"^[\s]*"
    r"(?P<tipo>" + _ACT_TIPO_ALT + r")"
    r"\s+N?\s*[º°o.]\s*"
    r"(?P<num>\d[\d.\s/]{0,30}\d|\d)",
    re.IGNORECASE | re.MULTILINE,
)

# Inserção de quebras de linha antes de cabeçalhos colados no meio de texto.
# pypdf às vezes concatena 2 linhas (especialmente layout multi-coluna) e o
# resultado é "fim da frase anterior.PORTARIA Nº 100" sem newline. Esse
# pré-processamento insere `\n` na fronteira para permitir o match com ^.
_ACT_BOUNDARY_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<=[\w.,;:)])(?=(?:" + _ACT_TIPO_ALT + r")\s+N?\s*[º°o.])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _ParsedAct:
    """Um ato extraído do PDF com cabeçalho identificado e texto bruto."""

    tipo: str
    numero: str
    titulo: str
    texto: str


@dataclass(frozen=True)
class _EdicaoMetadata:
    """Metadados da edição corrente do Diário."""

    caderno_id: int
    caderno_descricao: str
    data_publicacao: datetime
    secoes: list[dict[str, Any]]


def _normalize_for_match(text: str) -> str:
    """Mesma normalização de filters/keywords._normalize — NFKC + lower + ws collapse."""
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join(text.split())


class IOFMGCollector(BaseCollector):
    """Coleta atos do Diário Oficial Eletrônico de MG (Jornal Minas Gerais).

    YAML config (todos opcionais):
        selectors:
          caderno: "Diário do Executivo"   # default: Executivo
    """

    async def collect(self) -> list[RawItem]:
        if self._client is None:  # pragma: no cover - defensive, async with seta o client
            msg = f"{self.source.id}: collector deve ser usado com async with"
            raise CollectorError(msg)

        caderno_alvo = (self.source.selectors or {}).get("caderno", _DEFAULT_CADERNO)

        # 1. Auth — JWT anônimo descartável.
        jwt = await self._authenticate()

        # 2. Calendário — descobre id do caderno do dia.
        edicao_meta = await self._discover_edicao(caderno_alvo)

        # 3. Metadados + seções (índice de órgãos) — para enriquecer items.
        edicao_meta = await self._fetch_edicao_detail(edicao_meta)

        # 4. PDF — JSON com base64 do PKCS#7.
        pdf_bytes = await self._download_and_unwrap_pdf(edicao_meta.caderno_id, jwt)

        # 5. Extrai texto por página.
        full_text = self._extract_text(pdf_bytes)

        # 6. Fatia em atos.
        acts = list(self._parse_acts(full_text))
        if len(acts) > _MAX_ACTS_PER_RUN:  # pragma: no cover - defensive cap
            msg = (
                f"{self.source.id}: {len(acts)} atos excede MAX_ACTS_PER_RUN "
                f"({_MAX_ACTS_PER_RUN}) - abortando"
            )
            raise CollectorError(msg)

        # 7. Filtro local por org_mentions/keywords da source — rejeita cedo.
        filtered = self._filter_by_source_terms(acts)

        # 8. Build RawItems.
        items = [self._build_raw_item(a, edicao_meta) for a in filtered]
        logger.info(
            "iof_mg.collected",
            source=self.source.id,
            caderno=edicao_meta.caderno_descricao,
            data=edicao_meta.data_publicacao.date().isoformat(),
            atos_parseados=len(acts),
            atos_filtrados=len(filtered),
            items=len(items),
        )
        return items

    async def _authenticate(self) -> str:
        """POST anônimo retorna JWT efêmero. Falha = aborta (sem retry)."""
        if self._client is None:  # pragma: no cover - defensive, garantido por async with
            msg = f"{self.source.id}: collector deve ser usado com async with"
            raise CollectorError(msg)
        try:
            resp = await self._client.post(
                _AUTH_URL,
                json={},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            msg = f"{self.source.id}: auth falhou ({type(e).__name__})"
            raise CollectorError(msg) from e

        token = payload.get("dados") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            msg = f"{self.source.id}: auth retornou payload sem 'dados'"
            raise CollectorError(msg)
        # Não loga o token — structlog redactor cobre, mas defesa extra aqui.
        logger.info("iof_mg.authenticated", source=self.source.id, token_len=len(token))
        return token

    async def _discover_edicao(self, caderno_alvo: str) -> _EdicaoMetadata:
        """Lista cadernos do dia, escolhe o alvo (ex: 'Diário do Executivo')."""
        if self._client is None:  # pragma: no cover - defensive, garantido por async with
            msg = f"{self.source.id}: collector deve ser usado com async with"
            raise CollectorError(msg)
        try:
            resp = await self._client.get(_HOME_URL)
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as e:  # pragma: no cover - defensive
            msg = f"{self.source.id}: home endpoint falhou ({type(e).__name__})"
            raise CollectorError(msg) from e

        dados = payload.get("dados") if isinstance(payload, dict) else None
        if not isinstance(dados, dict):  # pragma: no cover - defensive
            msg = f"{self.source.id}: home retornou payload inesperado"
            raise CollectorError(msg)

        cadernos = dados.get("cadernosUltimaEdicao") or []
        if not isinstance(cadernos, list):  # pragma: no cover - defensive
            msg = f"{self.source.id}: cadernosUltimaEdicao não é list"
            raise CollectorError(msg)

        alvo_norm = _normalize_for_match(caderno_alvo)
        target = next(
            (c for c in cadernos if _normalize_for_match(str(c.get("descricao", ""))) == alvo_norm),
            None,
        )
        if target is None:
            disponveis = [c.get("descricao") for c in cadernos if isinstance(c, dict)]
            msg = (
                f"{self.source.id}: caderno {caderno_alvo!r} não encontrado. "
                f"Disponíveis: {disponveis}"
            )
            raise CollectorError(msg)

        caderno_id = target.get("id")
        if not isinstance(caderno_id, int):  # pragma: no cover - defensive
            msg = f"{self.source.id}: caderno sem 'id' int válido"
            raise CollectorError(msg)

        data_iso = dados.get("dataPublicacaoUltimaEdicao")
        try:
            data_pub = datetime.fromisoformat(str(data_iso))
        except (TypeError, ValueError) as e:  # pragma: no cover - API entrega ISO válido
            msg = f"{self.source.id}: dataPublicacao inválida: {data_iso!r}"
            raise CollectorError(msg) from e
        if data_pub.tzinfo is None:
            data_pub = data_pub.replace(tzinfo=UTC)

        return _EdicaoMetadata(
            caderno_id=caderno_id,
            caderno_descricao=str(target.get("descricao", "")),
            data_publicacao=data_pub,
            secoes=[],
        )

    async def _fetch_edicao_detail(self, meta: _EdicaoMetadata) -> _EdicaoMetadata:
        """Enriquece com secoes[] (cabeçalhos de órgão + paginaInicial)."""
        if self._client is None:  # pragma: no cover - defensive, garantido por async with
            msg = f"{self.source.id}: collector deve ser usado com async with"
            raise CollectorError(msg)
        url = _EDICAO_URL_TPL.format(id=meta.caderno_id)
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:  # noqa: BLE001 - fallback gracioso; secoes opcionais
            # Falha aqui não é fatal — seguimos sem o índice de órgãos.
            logger.warning(  # pragma: no cover - graceful, no impact on collected items
                "iof_mg.edicao_detail_failed",
                source=self.source.id,
                error=type(e).__name__,
            )
            return meta  # pragma: no cover

        dados = payload.get("dados") if isinstance(payload, dict) else None
        if not isinstance(dados, dict):  # pragma: no cover - defensive
            return meta
        cadernos = dados.get("cadernos") or []
        if not isinstance(cadernos, list) or not cadernos:  # pragma: no cover - defensive
            return meta
        # API retorna um array com 1 caderno (o solicitado).
        first = cadernos[0]
        secoes = first.get("secoes") if isinstance(first, dict) else None
        if not isinstance(secoes, list):  # pragma: no cover - defensive
            return meta

        return _EdicaoMetadata(
            caderno_id=meta.caderno_id,
            caderno_descricao=meta.caderno_descricao,
            data_publicacao=meta.data_publicacao,
            secoes=[s for s in secoes if isinstance(s, dict)],
        )

    async def _download_and_unwrap_pdf(self, caderno_id: int, jwt: str) -> bytes:
        """Baixa envelope, valida tamanho, decodifica base64, extrai PDF interno."""
        if self._client is None:  # pragma: no cover - defensive, garantido por async with
            msg = f"{self.source.id}: collector deve ser usado com async with"
            raise CollectorError(msg)
        url = _PDF_URL_TPL.format(id=caderno_id)
        try:
            resp = await self._client.get(
                url,
                headers={"Authorization": f"Bearer {jwt}"},
                # PDF de 5 MB em conexão lenta requer mais que 30s default.
                timeout=limits.HTTP_TIMEOUT_SECONDS * 4,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:  # pragma: no cover - defensive
            msg = f"{self.source.id}: download PDF falhou ({type(e).__name__})"
            raise CollectorError(msg) from e

        # Lê content-length se disponível; senão, lê todo body (com cap).
        body_bytes = resp.content
        if len(body_bytes) > _MAX_ENVELOPE_BYTES:  # pragma: no cover - defensive cap
            msg = (
                f"{self.source.id}: envelope {len(body_bytes)} bytes excede "
                f"MAX_ENVELOPE_BYTES ({_MAX_ENVELOPE_BYTES})"
            )
            raise CollectorError(msg)

        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:  # pragma: no cover - API JSON
            msg = f"{self.source.id}: PDF endpoint não retornou JSON ({type(e).__name__})"
            raise CollectorError(msg) from e

        dados = payload.get("dados") if isinstance(payload, dict) else None
        arquivo_b64 = dados.get("arquivo") if isinstance(dados, dict) else None
        if not isinstance(arquivo_b64, str) or not arquivo_b64:
            msg = f"{self.source.id}: PDF endpoint sem campo 'arquivo' (base64)"
            raise CollectorError(msg)

        try:
            envelope = base64.b64decode(arquivo_b64, validate=True)
        except (binascii.Error, ValueError) as e:
            msg = f"{self.source.id}: base64 do PDF inválido"
            raise CollectorError(msg) from e

        return _unwrap_pkcs7_to_pdf(envelope, source_id=self.source.id)

    def _extract_text(self, pdf_bytes: bytes) -> str:
        """Extrai texto de todas as páginas, junta com separador de página."""
        try:
            import pypdf  # noqa: PLC0415

            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        except Exception as e:
            msg = f"{self.source.id}: pypdf não conseguiu abrir o PDF ({type(e).__name__})"
            raise CollectorError(msg) from e

        page_texts: list[str] = []
        for idx, page in enumerate(reader.pages):
            try:
                txt = page.extract_text() or ""
            except Exception as e:  # noqa: BLE001 - pypdf lança vários tipos
                logger.warning(  # pragma: no cover - per-page fallback é raro
                    "iof_mg.page_extract_failed",
                    source=self.source.id,
                    page=idx + 1,
                    error=type(e).__name__,
                )
                txt = ""  # pragma: no cover
            page_texts.append(txt)
        return "\n\n[PAGE-BREAK]\n\n".join(page_texts)

    def _parse_acts(self, full_text: str) -> list[_ParsedAct]:
        """Encontra cabeçalhos de atos e fatia o texto entre cabeçalhos consecutivos."""
        # pypdf às vezes concatena linhas; injeta \n antes de cabeçalhos.
        full_text = _ACT_BOUNDARY_RE.sub("\n", full_text)
        matches = list(_ACT_HEADER_RE.finditer(full_text))
        if not matches:
            return []

        acts: list[_ParsedAct] = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
            ato_text = full_text[start:end][:_MAX_ACT_TEXT_BYTES]

            # Título = primeira linha não-vazia do ato (truncada para MAX_TITLE_LENGTH).
            first_line = next(
                (line.strip() for line in ato_text.splitlines() if line.strip()),
                "",
            )
            titulo = first_line[: limits.MAX_TITLE_LENGTH]

            tipo = (m.group("tipo") or "").strip().upper()
            numero = (m.group("num") or "").strip()
            # Normalize numero: collapse internal whitespace, strip trailing dots.
            numero = " ".join(numero.split()).rstrip(".")

            acts.append(_ParsedAct(tipo=tipo, numero=numero, titulo=titulo, texto=ato_text))
        return acts

    def _filter_by_source_terms(self, acts: list[_ParsedAct]) -> list[_ParsedAct]:
        """Aplica `org_mentions` (+ keywords_required) localmente para rejeitar cedo.

        O orquestrador chamará `filter_by_keywords` depois, mas filtrar aqui evita
        gerar 500 RawItem/dia que seriam descartados.
        """
        org_terms = list(self.source.org_mentions or [])
        kw_terms = list(self.source.keywords_required or [])
        # Sem org_mentions e sem keywords_required, deixa passar tudo —
        # o orquestrador aplica KEYWORDS_DEFAULT depois.
        if not org_terms and not kw_terms:
            return acts

        out: list[_ParsedAct] = []
        for a in acts:
            haystack = f"{a.titulo}\n{a.texto}"
            matched_org = False
            matched_kw = False
            if org_terms:
                matched_org, _ = matches_keywords(haystack, org_terms)
            if not matched_org and kw_terms:
                matched_kw, _ = matches_keywords(haystack, kw_terms)
            if matched_org or matched_kw:
                out.append(a)
        return out

    def _build_raw_item(self, ato: _ParsedAct, edicao: _EdicaoMetadata) -> RawItem:
        """Constrói RawItem para um ato. URL é deeplink da edição.

        Para o `content_hash`, usa SHA256 do texto do ato — estável entre runs
        do mesmo dia, mas distinto entre dias (data está dentro do texto).
        """
        titulo_full = ato.titulo if ato.titulo else f"{ato.tipo} {ato.numero}".strip()

        # Deeplink: dados JSON urlencoded. Mantém URL <= MAX_URL_LENGTH (2048).
        dados_obj = {
            "idCadernoEdicaoSelecionado": edicao.caderno_id,
            "dataPublicacaoSelecionada": edicao.data_publicacao.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        import urllib.parse  # noqa: PLC0415

        deeplink = _DEEPLINK_TPL.format(
            dados=urllib.parse.quote(json.dumps(dados_obj, separators=(",", ":")))
        )
        deeplink = deeplink[: limits.MAX_URL_LENGTH]

        return self.make_raw_item(
            titulo=titulo_full,
            url=deeplink,
            texto=ato.texto,
            data_pub=edicao.data_publicacao,
            content_for_hash=ato.texto,
            # Texto vem do PDF (não HTML); sanitize_html não tem o que fazer.
            sanitize=False,
        )


def _unwrap_pkcs7_to_pdf(envelope: bytes, *, source_id: str) -> bytes:
    """Extrai bytes do PDF de um envelope PKCS#7 SignedData.

    Estratégia simples sem validar assinatura: busca os bytes literais
    `%PDF-` (start) e o último `%%EOF` (end). Funciona pois PKCS#7 SignedData
    com content-type=data carrega o PDF inteiro como conteúdo encapsulado, sem
    transformação. Validação criptográfica fica para fase 2 (ver
    `docs/iof-mg-architecture.md`).
    """
    pdf_start = envelope.find(_PDF_MAGIC)
    if pdf_start < 0:
        msg = f"{source_id}: envelope não contém %PDF- (não é PKCS#7 esperado)"
        raise CollectorError(msg)
    eof_idx = envelope.rfind(_PDF_EOF)
    pdf_end = (eof_idx + len(_PDF_EOF)) if eof_idx > pdf_start else len(envelope)
    pdf = envelope[pdf_start:pdf_end]
    if len(pdf) > limits.MAX_PDF_BYTES:
        msg = (
            f"{source_id}: PDF interno {len(pdf)} bytes excede MAX_PDF_BYTES "
            f"({limits.MAX_PDF_BYTES})"
        )
        raise CollectorError(msg)
    return pdf
