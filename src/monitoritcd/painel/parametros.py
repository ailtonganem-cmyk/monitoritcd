"""Parâmetros de pesquisa (keywords extras) persistidos localmente."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any

from monitoritcd.core.models import Topic
from monitoritcd.filters.keywords import KEYWORDS_BY_TOPIC, KEYWORDS_DEFAULT, expand_with_extras

ARQUIVO = "keywords_extra.json"


def listar_parametros(raiz: Path) -> dict[str, Any]:
    extras: list[str] = []
    from monitoritcd.painel.persistencia import ler_json  # noqa: PLC0415

    data = ler_json(raiz, ARQUIVO)
    extras = [str(x) for x in data.get("extras", []) if str(x).strip()]
    por_topico = {t.value: list(KEYWORDS_BY_TOPIC[t]) for t in Topic}
    return {
        "defaults": list(KEYWORDS_DEFAULT),
        "extras": extras,
        "efetivos": list(expand_with_extras(extras)),
        "por_topico": por_topico,
    }


def gravar_extras(raiz: Path, extras: list[str]) -> dict[str, Any]:
    limpos: list[str] = []
    vistos: set[str] = set()
    for item in extras:
        kw = " ".join(str(item).split())
        if not kw or len(kw) > 80:  # noqa: PLR2004
            continue
        chave = kw.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        limpos.append(kw)
    from monitoritcd.painel.persistencia import gravar_json  # noqa: PLC0415

    gravar_json(raiz, ARQUIVO, {"extras": limpos})
    return listar_parametros(raiz)
