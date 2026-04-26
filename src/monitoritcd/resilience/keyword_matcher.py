"""Matcher otimizado de keywords (Sugestão #47).

Usa Aho-Corasick (`pyahocorasick`) quando disponível: O(text + matches).
Fallback para substring loop (mantido para zero-deps).

Acelera `filters/keywords.py` em cenários com muitas keywords (KEYWORDS_DEFAULT
tem ~30 termos vezes 27 UFs).
"""

from __future__ import annotations

from typing import Final

try:  # pragma: no cover - depende de instalação opcional
    import ahocorasick  # type: ignore[import-untyped]

    _AHC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AHC_AVAILABLE = False


class KeywordMatcher:
    """Pre-compiled keyword matcher.

    Uso:
        m = KeywordMatcher(["ITCD", "alíquota"])
        matched, found = m.find_in("texto sobre ITCD e alíquota...")
    """

    def __init__(self, keywords: list[str], *, case_sensitive: bool = False) -> None:
        self._keywords = list(keywords)
        self._case_sensitive = case_sensitive
        self._lower_keywords = [k.lower() for k in keywords] if not case_sensitive else None
        self._automaton = self._build_automaton() if _AHC_AVAILABLE else None

    def _build_automaton(self) -> object | None:
        """Constrói automaton AC (best effort)."""
        if not _AHC_AVAILABLE:
            return None
        a = ahocorasick.Automaton()
        keys = self._lower_keywords if self._lower_keywords is not None else self._keywords
        for idx, kw in enumerate(keys):
            if kw:
                a.add_word(kw, (idx, kw))
        a.make_automaton()
        return a

    def find_in(self, text: str) -> tuple[bool, list[str]]:
        """Retorna (any_match, lista de keywords encontradas, sem duplicatas)."""
        if not text or not self._keywords:
            return False, []

        if self._automaton is not None:
            # Caminho rápido — Aho-Corasick
            haystack = text if self._case_sensitive else text.lower()
            found: set[str] = set()
            for _end, (_idx, kw) in self._automaton.iter(haystack):  # type: ignore[attr-defined]
                found.add(kw)
            return bool(found), sorted(found)

        # Fallback: substring loop O(text * keywords)
        haystack = text if self._case_sensitive else text.lower()
        found_list: list[str] = []
        seen: set[str] = set()
        keys = self._lower_keywords if self._lower_keywords is not None else self._keywords
        for kw in keys:
            if kw and kw in haystack and kw not in seen:
                seen.add(kw)
                found_list.append(kw)
        return bool(found_list), found_list

    @property
    def using_aho_corasick(self) -> bool:
        """True quando o caminho rápido está ativo (testes diferenciam)."""
        return self._automaton is not None


# Constantes públicas
AHO_CORASICK_AVAILABLE: Final[bool] = _AHC_AVAILABLE
