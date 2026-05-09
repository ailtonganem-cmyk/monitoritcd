"""Coletor para Assembleia Legislativa de São Paulo (ALESP).

Endpoint público de **dados abertos**: ZIP diário com a base completa de
proposituras (PLs, PECs, Mensagens, Indicações, etc.).

URL canônica: `https://www.al.sp.gov.br/repositorioDados/processo_legislativo/proposituras.zip`

Características do dataset (validado 2026-05-08):
- Tamanho do ZIP: ~16 MB (atualizado diariamente).
- XML descompactado: ~128 MB com ~270 mil proposituras de 1996 até hoje.
- Schema:
  ```xml
  <propositura>
    <AnoLegislativo>2026</AnoLegislativo>
    <CodOriginalidade>...</CodOriginalidade>
    <Ementa>texto da proposta</Ementa>
    <DtEntradaSistema>2026-04-08T00:00:00-03:00</DtEntradaSistema>
    <DtPublicacao>2026-04-08T00:00:00-03:00</DtPublicacao>
    <IdDocumento>1000685241</IdDocumento>
    <IdNatureza>1</IdNatureza>      <!-- 1=PL, 2=PEC, 9=Indicação, etc. -->
    <NroLegislativo>309</NroLegislativo>
  </propositura>
  ```
- URL pública por documento: `https://www.al.sp.gov.br/propositura/?id={IdDocumento}`.

A ALESP usa SharePoint/ASP.NET no portal de pesquisa — cliente HTML estático
não consegue parsear (VIEWSTATE). O ZIP de dados abertos é o caminho oficial.

Estratégia do coletor (memória-eficiente):
1. Download streaming do ZIP (tamanho hard-cap em `MAX_OPEN_DATA_BYTES`).
2. `zipfile.ZipFile.open()` em modo streaming.
3. `xml.etree.ElementTree.iterparse()` lê eventos `end` para `<propositura>`.
4. Filtra por `DtEntradaSistema >= cutoff` (últimos N dias).
5. Filtra por keywords no `Ementa` (case-insensitive).
6. `elem.clear()` libera memória após cada item.

Princípios canônicos aplicados:
1. **MAX_BYTES**: ZIP limitado a `MAX_OPEN_DATA_BYTES` (50 MB).
2. **MAX_DEPTH**: streaming parse não constrói árvore — defesa natural.
3. **Validação anti-SSRF**: BaseCollector.fetch valida URL antes de fetch.
4. **Defense-in-depth XML**: `defusedxml.ElementTree` previne XXE/billion-laughs.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Self

import httpx
import structlog
from defusedxml import ElementTree as DefusedET  # type: ignore[import-untyped]

from monitoritcd.core import limits
from monitoritcd.core.base_collector import (
    USER_AGENT,
    BaseCollector,
    CollectorError,
    _domain_of,
    _DomainRateLimiter,
)
from monitoritcd.security.url_validator import validate_url

if TYPE_CHECKING:
    from monitoritcd.core.models import RawItem

logger = structlog.get_logger(__name__)

DEFAULT_KEYWORDS: tuple[str, ...] = (
    "ITCMD",
    "ITCD",
    "causa mortis",
    "transmissão",
    "doação",
    "sucessão",
    "inventário",
    "regime de bens",
)
DEFAULT_DIAS_RECENTES = 60
DEFAULT_MAX_ITEMS = 500
ALESP_PUBLIC_URL = "https://www.al.sp.gov.br/propositura/?id="
PROPOSITURAS_XML_NAME = "proposituras.xml"

# IdNatureza → nome do tipo (referência ALESP).
# Documentado em https://www.al.sp.gov.br/dados-abertos/recurso/44 (naturezasSpl.xml).
NATUREZA_NOMES: dict[str, str] = {
    "1": "Projeto de Lei",
    "2": "Proposta de Emenda Constitucional",
    "3": "Projeto de Lei Complementar",
    "4": "Projeto de Resolução",
    "5": "Projeto de Decreto Legislativo",
    "6": "Mensagem",
    "7": "Veto",
    "8": "Substitutivo",
    "9": "Indicação",
    "10": "Requerimento",
}


class ALESPCollector(BaseCollector):
    """Collector ALESP via download do ZIP de proposituras.

    YAML config esperado em `selectors`:
        palavras_chave: "ITCMD|ITCD|..."   (opcional; default: DEFAULT_KEYWORDS)
        dias: int                           (opcional; default: 60)
        max_items: int                      (opcional; default: 500)
        naturezas: "1,2,3"                  (opcional; CSV de IdNatureza; default: todas)
    """

    async def __aenter__(self) -> Self:
        """Override: client com Accept binário (ZIP) e timeout extendido."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(limits.HTTP_TIMEOUT_SECONDS * 2),
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/zip, application/octet-stream;q=0.9, */*;q=0.5",
                },
                follow_redirects=True,
                max_redirects=5,
            )
        return self

    async def collect(self) -> list[RawItem]:
        sel = self.source.selectors or {}

        kw_raw = sel.get("palavras_chave") or "|".join(DEFAULT_KEYWORDS)
        palavras = [p.strip().lower() for p in kw_raw.split("|") if p.strip()]
        if not palavras:
            msg = f"palavras_chave vazia em {self.source.id}"
            raise CollectorError(msg)

        try:
            dias = int(sel.get("dias", str(DEFAULT_DIAS_RECENTES)))
        except (TypeError, ValueError) as e:
            msg = f"dias inválido em {self.source.id}: {e}"
            raise CollectorError(msg) from e

        try:
            max_items = int(sel.get("max_items", str(DEFAULT_MAX_ITEMS)))
        except (TypeError, ValueError) as e:
            msg = f"max_items inválido em {self.source.id}: {e}"
            raise CollectorError(msg) from e

        naturezas_raw = (sel.get("naturezas") or "").strip()
        allowed_naturezas: set[str] | None = None
        if naturezas_raw:
            allowed_naturezas = {n.strip() for n in naturezas_raw.split(",") if n.strip()}

        cutoff = datetime.now(UTC) - timedelta(days=dias)

        try:
            zip_bytes = await self._fetch_zip()
        except (CollectorError, httpx.HTTPError) as e:
            logger.warning(
                "alesp.fetch_failed",
                source=self.source.id,
                error_type=type(e).__name__,
                error=str(e) or "no message",
            )
            return []

        try:
            items = self._parse_zip(
                zip_bytes,
                palavras=palavras,
                cutoff=cutoff,
                max_items=max_items,
                allowed_naturezas=allowed_naturezas,
            )
        except (zipfile.BadZipFile, OSError, CollectorError) as e:
            # CollectorError aqui = ZIP válido mas sem proposituras.xml
            # (estrutura inesperada do dataset, ex: nome do arquivo mudou).
            logger.warning(
                "alesp.parse_failed",
                source=self.source.id,
                error_type=type(e).__name__,
                error=str(e),
            )
            return []

        logger.info(
            "alesp.collected",
            source=self.source.id,
            count=len(items),
            keywords=len(palavras),
            dias=dias,
        )
        return items

    async def _fetch_zip(self) -> bytes:
        """Download do ZIP com size cap aplicado em streaming."""
        target = self.source.url
        validate_url(target)

        if self._client is None:
            msg = "BaseCollector deve ser usado com `async with` ou http_client explícito"
            raise CollectorError(msg)

        domain = _domain_of(target)
        await _DomainRateLimiter.acquire(domain, limits.DOMAIN_REQUESTS_INTERVAL_SECONDS)

        client = self._client
        max_bytes = limits.MAX_OPEN_DATA_BYTES

        # Streaming-download com hard cap. Se exceder, aborta — defesa contra
        # respostas anômalas (zip malicioso ou crescimento explosivo do dataset).
        async with client.stream("GET", target) as response:
            response.raise_for_status()
            buf = bytearray()
            async for chunk in response.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    msg = f"download excedeu MAX_OPEN_DATA_BYTES ({max_bytes}) em {self.source.id}"
                    raise CollectorError(msg)
        return bytes(buf)

    def _parse_zip(
        self,
        zip_bytes: bytes,
        *,
        palavras: list[str],
        cutoff: datetime,
        max_items: int,
        allowed_naturezas: set[str] | None,
    ) -> list[RawItem]:
        """Streaming-parse XML dentro do ZIP com filtros."""
        items: list[RawItem] = []
        records_processed = 0

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            try:
                inner = zf.open(PROPOSITURAS_XML_NAME, "r")
            except KeyError as e:
                msg = f"ZIP não contém {PROPOSITURAS_XML_NAME}: {e}"
                raise CollectorError(msg) from e

            with inner:
                # iterparse com defusedxml previne XXE / billion-laughs
                # (defusedxml's iterparse é seguro por design).
                context = DefusedET.iterparse(inner, events=("end",))
                for _event, elem in context:
                    if elem.tag != "propositura":
                        continue

                    records_processed += 1
                    if records_processed > limits.MAX_OPEN_DATA_RECORDS:
                        # Guard rail: payload anômalo
                        logger.warning(
                            "alesp.records_cap",
                            source=self.source.id,
                            cap=limits.MAX_OPEN_DATA_RECORDS,
                        )
                        break

                    item = self._parse_propositura(
                        elem,
                        palavras=palavras,
                        cutoff=cutoff,
                        allowed_naturezas=allowed_naturezas,
                    )
                    if item is not None:
                        items.append(item)
                        if len(items) >= max_items:
                            elem.clear()
                            break

                    # Libera memória após processar
                    elem.clear()

        return items

    def _parse_propositura(
        self,
        elem: object,
        *,
        palavras: list[str],
        cutoff: datetime,
        allowed_naturezas: set[str] | None,
    ) -> RawItem | None:
        # ElementTree element — usar findtext que retorna str|None
        find = elem.findtext  # type: ignore[attr-defined]

        ementa = (find("Ementa") or "").strip()
        if not ementa:
            return None

        # Filtro 1: keywords (cliente-side)
        ementa_lower = ementa.lower()
        if not any(p in ementa_lower for p in palavras):
            return None

        # Filtro 2: data — DtEntradaSistema é a data de inserção no sistema
        # (mais confiável que DtPublicacao para detectar movimento recente).
        dt_str = find("DtEntradaSistema") or find("DtPublicacao") or ""
        try:
            dt = datetime.fromisoformat(dt_str)
        except ValueError:
            dt = None
        if dt is not None and dt < cutoff:
            return None

        # Filtro 3: natureza (opcional)
        natureza = (find("IdNatureza") or "").strip()
        if allowed_naturezas is not None and natureza not in allowed_naturezas:
            return None

        # Construção do item
        id_doc = (find("IdDocumento") or "").strip()
        nro = (find("NroLegislativo") or "").strip()
        ano = (find("AnoLegislativo") or "").strip()
        if not (id_doc and nro and ano):
            return None

        natureza_nome = NATUREZA_NOMES.get(natureza, f"Tipo {natureza}" if natureza else "")
        titulo = f"{natureza_nome} {nro}/{ano}" if natureza_nome else f"Propositura {nro}/{ano}"

        url = f"{ALESP_PUBLIC_URL}{id_doc}"
        # ID estável para hash (mesma propositura entre execuções gera mesmo hash)
        content_id = f"alesp:{id_doc}"

        return self.make_raw_item(
            titulo=titulo,
            url=url,
            texto=ementa,
            data_pub=dt,
            content_for_hash=content_id,
        )
