"""Testes unitários para o gate Jev shadow / act de documentos críticos."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from monitoritcd.core.models import (
    Documento,
    LLMResult,
    Parser,
    RawItem,
    SeverityTier,
    Source,
    TipoAto,
    TipoFonte,
)
from monitoritcd.observability.jev_shadow_critico import (
    EXIT_CODE_ALLOW,
    EXIT_CODE_DENY,
    _wrapper_path,
    act_critico_decision,
    build_shadow_state,
    filter_criticos_for_notify,
    shadow_critico_vs_digest,
    shadow_criticos,
)

NOW = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)


def _make_doc(
    doc_id: str = "doc-1",
    *,
    has_llm: bool = True,
    severity: SeverityTier = SeverityTier.CRITICO,
    title: str = "Lei 1234/2026 altera alíquota do ITCD",
    resumo: str = "Altera alíquota de 4% para 8%",
) -> Documento:
    src = Source(
        id="src-mg",
        uf="MG",
        nome="DOE MG",
        tipo=TipoFonte.DOE,
        parser=Parser.GENERIC_HTML,
        url="https://iof.mg.gov.br",
    )
    raw = RawItem(
        source_id="src-mg",
        url="https://iof.mg.gov.br/doc/1",
        titulo_raw=title,
        texto_raw="Texto completo",
        fetched_at=NOW,
        content_hash="0" * 64,
    )
    llm = (
        LLMResult(
            classified_at=NOW,
            llm_model="gemini-2.5-flash",
            llm_prompt_version="v2",
            tipo=TipoAto.LEI_SANCIONADA,
            relevancia=4,
            severity_tier=severity,
            resumo=resumo,
        )
        if has_llm
        else None
    )
    return Documento(
        doc_id=doc_id,
        owner_id="owner-test",
        source=src,
        original=raw,
        llm=llm,
    )


@pytest.mark.unit
class TestWrapperPath:
    def test_default_wrapper_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MONITORITCD_JEV_SHADOW_WRAPPER", raising=False)
        path = _wrapper_path()
        assert "monitor-itcd-shadow.sh" in str(path)

    def test_custom_wrapper_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        custom = tmp_path / "custom-wrapper.sh"
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW_WRAPPER", str(custom))
        path = _wrapper_path()
        assert path == custom


@pytest.mark.unit
class TestBuildShadowState:
    def test_build_state_with_llm(self) -> None:
        doc = _make_doc()
        state = build_shadow_state(doc)
        assert "doc_id=doc-1" in state
        assert "uf=MG" in state
        assert "source_id=src-mg" in state
        assert "url_host=iof.mg.gov.br" in state
        assert "title=Lei 1234/2026" in state
        assert "llm_severity=critico" in state
        assert "llm_tipo=lei_sancionada" in state
        assert "llm_relevancia=4" in state
        assert "llm_model=gemini-2.5-flash" in state
        assert "instruction_context:" in state

    def test_build_state_without_llm(self) -> None:
        doc = _make_doc(has_llm=False)
        state = build_shadow_state(doc)
        assert "doc_id=doc-1" in state
        assert "llm_severity=unknown" in state

    def test_build_state_truncates_long_fields(self) -> None:
        long_title = "A" * 500
        long_resumo = "B" * 1000
        doc = _make_doc(title=long_title, resumo=long_resumo)
        state = build_shadow_state(doc)
        # 240 chars de título e 400 de resumo
        assert ("title=" + "A" * 240) in state
        assert ("title=" + "A" * 241) not in state
        assert ("llm_resumo=" + "B" * 400) in state
        assert ("llm_resumo=" + "B" * 401) not in state

    def test_build_state_handles_urlparse_exception(self) -> None:
        doc = _make_doc()
        patch_target = "monitoritcd.observability.jev_shadow_critico.urlparse"
        with patch(patch_target, side_effect=ValueError("bad url")):
            state = build_shadow_state(doc)
            assert "url_host=" in state


@pytest.mark.unit
class TestActCriticoDecision:
    def test_wrapper_missing_returns_fail_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing_script = tmp_path / "nonexistent.sh"
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW_WRAPPER", str(missing_script))
        doc = _make_doc()
        assert act_critico_decision(doc) == "fail_open"

    def test_disabled_by_env_returns_fail_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wrapper = tmp_path / "wrapper.sh"
        wrapper.touch()
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW_WRAPPER", str(wrapper))
        doc = _make_doc()

        for val in ["0", "false", "off", "FALSE"]:
            monkeypatch.setenv("MONITORITCD_JEV_SHADOW", val)
            assert act_critico_decision(doc) == "fail_open"

    def test_subprocess_allow(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        wrapper = tmp_path / "wrapper.sh"
        wrapper.touch()
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW_WRAPPER", str(wrapper))
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW", "1")
        doc = _make_doc()

        mock_proc = MagicMock(returncode=EXIT_CODE_ALLOW, stdout="allow reason")
        with patch("subprocess.run", return_value=mock_proc):
            assert act_critico_decision(doc) == "allow"

    def test_subprocess_deny(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        wrapper = tmp_path / "wrapper.sh"
        wrapper.touch()
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW_WRAPPER", str(wrapper))
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW", "1")
        doc = _make_doc()

        mock_proc = MagicMock(returncode=EXIT_CODE_DENY, stdout="deny reason")
        with patch("subprocess.run", return_value=mock_proc):
            assert act_critico_decision(doc) == "deny"

    def test_subprocess_unexpected_exit_code_returns_fail_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wrapper = tmp_path / "wrapper.sh"
        wrapper.touch()
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW_WRAPPER", str(wrapper))
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW", "1")
        doc = _make_doc()

        mock_proc = MagicMock(returncode=1, stdout="error")
        with patch("subprocess.run", return_value=mock_proc):
            assert act_critico_decision(doc) == "fail_open"

    def test_subprocess_exception_returns_fail_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wrapper = tmp_path / "wrapper.sh"
        wrapper.touch()
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW_WRAPPER", str(wrapper))
        monkeypatch.setenv("MONITORITCD_JEV_SHADOW", "1")
        doc = _make_doc()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="test", timeout=45)):
            assert act_critico_decision(doc) == "fail_open"


@pytest.mark.unit
class TestShadowCriticoVsDigest:
    def test_shadow_critico_vs_digest_bool_mapping(self) -> None:
        doc = _make_doc()
        target = "monitoritcd.observability.jev_shadow_critico.act_critico_decision"
        with patch(target, return_value="allow"):
            assert shadow_critico_vs_digest(doc) is True

        with patch(target, return_value="fail_open"):
            assert shadow_critico_vs_digest(doc) is True

        with patch(target, return_value="deny"):
            assert shadow_critico_vs_digest(doc) is False


@pytest.mark.unit
class TestFilterCriticosForNotify:
    def test_filter_criticos(self) -> None:
        doc_allow = _make_doc("doc-allow")
        doc_deny = _make_doc("doc-deny")
        doc_fail_open = _make_doc("doc-fail-open")

        def mock_decision(doc: Documento) -> str:
            if doc.doc_id == "doc-allow":
                return "allow"
            if doc.doc_id == "doc-deny":
                return "deny"
            return "fail_open"

        target = "monitoritcd.observability.jev_shadow_critico.act_critico_decision"
        with patch(target, side_effect=mock_decision):
            keep, downgrade = filter_criticos_for_notify([doc_allow, doc_deny, doc_fail_open])
            assert [d.doc_id for d in keep] == ["doc-allow", "doc-fail-open"]
            assert [d.doc_id for d in downgrade] == ["doc-deny"]

    def test_shadow_criticos_compat(self) -> None:
        docs = [_make_doc("doc-1"), _make_doc("doc-2")]
        target = "monitoritcd.observability.jev_shadow_critico.act_critico_decision"
        with patch(target) as mock_decide:
            shadow_criticos(docs)
            assert mock_decide.call_count == 2
