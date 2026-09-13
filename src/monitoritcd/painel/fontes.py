"""Catálogo e inclusão de fontes — YAML em `sources/`, seleção local."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from monitoritcd.core.limits import MAX_SOURCE_ID_LENGTH, UF_REGEX, VALID_UFS
from monitoritcd.core.models import Parser, Source, TipoFonte
from monitoritcd.core.source_loader import SourceConfigError, load_all_sources
from monitoritcd.security.url_validator import validate_url

_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
SELECAO_NOME = "fontes_selecao.json"
OPERADOR_DIR = "_operador"


def _repo_root() -> Path:
    env = os.environ.get("MONITORITCD_ROOT", "").strip()
    return Path(env) if env else Path(__file__).resolve().parents[3]


def dir_sources(raiz: Path | None = None) -> Path:
    return (raiz or _repo_root()) / "sources"


def dir_config(raiz: Path | None = None) -> Path:
    return (raiz or _repo_root()) / "config" / "painel"


def _ler_selecao(raiz: Path) -> dict[str, bool]:
    path = dir_config(raiz) / SELECAO_NOME
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(k): bool(v) for k, v in data.items()}


def _gravar_selecao(raiz: Path, mapa: dict[str, bool]) -> None:
    pasta = dir_config(raiz)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / SELECAO_NOME).write_text(
        json.dumps(mapa, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _slug_fonte(fonte_id: str) -> str:
    """Slug canônico; rejeita path traversal e id fora do padrão."""
    matched = _ID_RE.fullmatch(fonte_id.strip().lower())
    if matched is None:
        raise SourceConfigError("id inválido (use slug a-z, 0-9, hífen)")
    sid = os.path.basename(matched.group(0))  # noqa: PTH119 — sanitizer CodeQL
    if not _ID_RE.fullmatch(sid) or ".." in sid or "/" in sid or "\\" in sid:
        raise SourceConfigError("id inválido (use slug a-z, 0-9, hífen)")
    return sid


def _pasta_operador(root: Path) -> Path:
    pasta = (dir_sources(root) / OPERADOR_DIR).resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _yaml_operador(root: Path, fonte_id: str) -> Path:
    sid = _slug_fonte(fonte_id)
    pasta = _pasta_operador(root)
    for candidato in pasta.iterdir():
        if candidato.suffix == ".yaml" and candidato.stem == sid:
            return candidato.resolve()
    nome = os.path.basename(sid + ".yaml")
    destino = (pasta / nome).resolve()
    if destino.parent != pasta:
        raise SourceConfigError("id inválido (use slug a-z, 0-9, hífen)")
    return destino


def listar_fontes(raiz: Path | None = None) -> list[dict[str, Any]]:
    """Catálogo YAML + flag `selecionada` (overlay local, como no Coletor)."""
    root = raiz or _repo_root()
    fontes = load_all_sources(dir_sources(root), ativo_only=False)
    selecao = _ler_selecao(root)
    op_ids = {p.stem for p in (dir_sources(root) / OPERADOR_DIR).glob("*.yaml")}
    itens: list[dict[str, Any]] = []
    for src in fontes:
        selecionada = selecao.get(src.id, src.ativo)
        itens.append(
            {
                "id": src.id,
                "uf": src.uf,
                "nome": src.nome,
                "tipo": src.tipo.value,
                "parser": src.parser.value,
                "url": src.url,
                "ativo_yaml": src.ativo,
                "selecionada": selecionada,
                "fragile": src.fragile,
                "operador": src.id in op_ids,
            }
        )
    itens.sort(key=lambda i: (i["uf"], i["id"]))
    return itens


def selecionar_fonte(
    fonte_id: str, selecionada: bool, *, raiz: Path | None = None
) -> dict[str, Any]:
    root = raiz or _repo_root()
    ids = {s["id"] for s in listar_fontes(root)}
    if fonte_id not in ids:
        raise SourceConfigError(f"fonte desconhecida: {fonte_id}")
    mapa = _ler_selecao(root)
    mapa[fonte_id] = bool(selecionada)
    _gravar_selecao(root, mapa)
    return next(s for s in listar_fontes(root) if s["id"] == fonte_id)


def incluir_fonte(
    *,
    fonte_id: str,
    uf: str,
    nome: str,
    url: str,
    parser: str = Parser.GENERIC_HTML.value,
    tipo: str = TipoFonte.NOTICIA.value,
    raiz: Path | None = None,
) -> dict[str, Any]:
    """Grava YAML em `sources/_operador/` e marca selecionada."""
    root = raiz or _repo_root()
    sid = _slug_fonte(fonte_id)
    if len(sid) > MAX_SOURCE_ID_LENGTH:
        raise SourceConfigError("id inválido (use slug a-z, 0-9, hífen)")
    uf_n = uf.strip()
    if not re.match(UF_REGEX, uf_n):
        raise SourceConfigError("UF inválida")
    validate_url(url)
    existentes = {s["id"] for s in listar_fontes(root)}
    if sid in existentes:
        raise SourceConfigError(f"id duplicado: {sid}")
    try:
        parser_e = Parser(parser)
        tipo_e = TipoFonte(tipo)
    except ValueError as exc:
        raise SourceConfigError("parser ou tipo inválido") from exc
    payload = {
        "id": sid,
        "uf": uf_n,
        "nome": nome.strip()[:200],
        "tipo": tipo_e.value,
        "parser": parser_e.value,
        "url": url.strip(),
        "ativo": True,
        "notas": "Incluída pelo painel local (operador).",
    }
    Source.model_validate(payload)
    destino = _yaml_operador(root, sid)
    destino.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    selecionar_fonte(sid, True, raiz=root)
    return next(s for s in listar_fontes(root) if s["id"] == sid)


def excluir_fonte(fonte_id: str, *, raiz: Path | None = None) -> None:
    """Remove só YAML do operador; catálogo versionado não apaga."""
    root = raiz or _repo_root()
    sid = _slug_fonte(fonte_id)
    pasta = _pasta_operador(root)
    alvo: Path | None = None
    for candidato in pasta.iterdir():
        if candidato.suffix == ".yaml" and candidato.stem == sid:
            alvo = candidato
            break
    if alvo is None or not alvo.is_file():
        raise SourceConfigError("só fontes incluídas pelo painel podem ser excluídas")
    alvo.unlink()
    mapa = _ler_selecao(root)
    mapa.pop(sid, None)
    _gravar_selecao(root, mapa)


def ufs_validas() -> tuple[str, ...]:
    return (*VALID_UFS, "_federal")
