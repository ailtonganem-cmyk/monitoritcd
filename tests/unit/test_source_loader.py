"""Testes do `source_loader`.

Cobre:
- YAMLs válidos carregam como Source
- URLs maliciosas (anti-SSRF) são rejeitadas
- YAML mal-formado falha loudly
- IDs duplicados rejeitados
- ativo_only filtra
- MAX_YAML_DEPTH enforcement
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from monitoritcd.core.source_loader import (
    SourceConfigError,
    load_all_sources,
    load_source,
)


def _write_yaml(path: Path, content: str) -> Path:
    path.write_text(dedent(content), encoding="utf-8")
    return path


VALID_YAML = """
id: test-src
uf: SP
nome: "Teste"
tipo: sefaz
parser: generic_html
url: "https://portal.fazenda.sp.gov.br/"
keywords_required:
  - ITCMD
selectors:
  item: "div"
  titulo: "h3"
  link: "a@href"
ativo: true
"""


@pytest.mark.unit
class TestLoadSource:
    def test_valid_yaml_loads(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path / "src.yaml", VALID_YAML)
        src = load_source(path)
        assert src.id == "test-src"
        assert src.uf == "SP"
        assert src.ativo is True

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SourceConfigError, match="não encontrado"):
            load_source(tmp_path / "missing.yaml")

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path / "bad.yaml", ":: not yaml ::")
        with pytest.raises(SourceConfigError):
            load_source(path)

    def test_yaml_not_dict_raises(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path / "list.yaml", "- item1\n- item2\n")
        with pytest.raises(SourceConfigError, match="mapping"):
            load_source(path)

    def test_url_with_localhost_rejected(self, tmp_path: Path) -> None:
        bad = VALID_YAML.replace("https://portal.fazenda.sp.gov.br/", "https://localhost/")
        path = _write_yaml(tmp_path / "ssrf.yaml", bad)
        with pytest.raises(SourceConfigError, match="não-segura"):
            load_source(path)

    def test_url_http_rejected(self, tmp_path: Path) -> None:
        bad = VALID_YAML.replace("https://", "http://")
        path = _write_yaml(tmp_path / "http.yaml", bad)
        with pytest.raises(SourceConfigError, match="não-segura"):
            load_source(path)

    def test_invalid_uf_rejected(self, tmp_path: Path) -> None:
        bad = VALID_YAML.replace("uf: SP", "uf: XX")  # XX não é UF válida
        path = _write_yaml(tmp_path / "uf.yaml", bad)
        with pytest.raises(SourceConfigError, match="Schema"):
            load_source(path)

    def test_extra_field_rejected(self, tmp_path: Path) -> None:
        bad = VALID_YAML + "extra_unknown: oops\n"
        path = _write_yaml(tmp_path / "extra.yaml", bad)
        with pytest.raises(SourceConfigError, match="Schema"):
            load_source(path)

    def test_yaml_too_deep_rejected(self, tmp_path: Path) -> None:
        # 8 níveis de aninhamento — excede MAX_YAML_DEPTH=6
        deep = (
            "a:\n  b:\n    c:\n      d:\n"
            "        e:\n          f:\n            g:\n              h: x\n"
        )
        path = _write_yaml(tmp_path / "deep.yaml", deep)
        with pytest.raises(SourceConfigError, match="MAX_YAML_DEPTH"):
            load_source(path)


@pytest.mark.unit
class TestLoadAllSources:
    def test_loads_all_yamls(self, tmp_path: Path) -> None:
        (tmp_path / "_federal").mkdir()
        (tmp_path / "SP").mkdir()
        _write_yaml(
            tmp_path / "_federal" / "fed.yaml",
            VALID_YAML.replace("test-src", "fed-src").replace("uf: SP", "uf: _federal"),
        )
        _write_yaml(tmp_path / "SP" / "sp.yaml", VALID_YAML.replace("test-src", "sp-src"))

        sources = load_all_sources(tmp_path)
        assert len(sources) == 2
        assert {s.id for s in sources} == {"fed-src", "sp-src"}

    def test_directory_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SourceConfigError, match="não existe"):
            load_all_sources(tmp_path / "nonexistent")

    def test_duplicate_id_rejected(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path / "a.yaml", VALID_YAML)
        _write_yaml(tmp_path / "b.yaml", VALID_YAML)  # mesmo id
        with pytest.raises(SourceConfigError, match="duplicado"):
            load_all_sources(tmp_path)

    def test_ativo_only_filters_inactive(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "active.yaml",
            VALID_YAML.replace("test-src", "active"),
        )
        _write_yaml(
            tmp_path / "inactive.yaml",
            VALID_YAML.replace("test-src", "inactive").replace("ativo: true", "ativo: false"),
        )
        sources = load_all_sources(tmp_path, ativo_only=True)
        assert len(sources) == 1
        assert sources[0].id == "active"

    def test_ativo_only_false_includes_all(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "active.yaml",
            VALID_YAML.replace("test-src", "active"),
        )
        _write_yaml(
            tmp_path / "inactive.yaml",
            VALID_YAML.replace("test-src", "inactive").replace("ativo: true", "ativo: false"),
        )
        sources = load_all_sources(tmp_path, ativo_only=False)
        assert len(sources) == 2

    def test_loads_real_lexml_yaml(self) -> None:
        """Smoke test: o YAML real em sources/_federal/lexml.yaml é válido."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        lexml_yaml = repo_root / "sources" / "_federal" / "lexml.yaml"
        if lexml_yaml.exists():
            src = load_source(lexml_yaml)
            assert src.id == "lexml-federal"
            assert src.parser.value == "lexml"
            assert src.uf == "_federal"

    def test_loads_all_real_sources(self) -> None:
        """Smoke test: todos os YAMLs reais em sources/ são válidos.

        Falha aqui = regressão que CI deve pegar.
        """
        repo_root = Path(__file__).resolve().parent.parent.parent
        sources_dir = repo_root / "sources"
        if not sources_dir.is_dir():
            return
        sources = load_all_sources(sources_dir)
        # Sanity: temos ≥ 1 fonte e ≥ LexML
        assert len(sources) >= 1
        ids = {s.id for s in sources}
        assert "lexml-federal" in ids

    def test_real_tribunais_yamls_present(self) -> None:
        """Verifica que YAMLs de tribunais foram criados."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        federal_dir = repo_root / "sources" / "_federal"
        if not federal_dir.is_dir():
            return
        expected = {
            "stf.yaml",
            "stj.yaml",
            "trf1.yaml",
            "trf2.yaml",
            "trf3.yaml",
            "trf4.yaml",
            "trf5.yaml",
            "trf6.yaml",
        }
        existing = {p.name for p in federal_dir.glob("*.yaml")}
        missing = expected - existing
        assert not missing, f"YAMLs de tribunais faltando: {missing}"
