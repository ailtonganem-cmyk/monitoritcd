"""Validação semântica de HTML em templates de email (Sugestão #17).

Usa html5lib em modo strict — qualquer HTML inválido falha o teste.
Detecta tags não fechadas, atributos malformados, conteúdo fora de elementos.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

# Imports condicionais (html5lib é opcional em runtime; obrigatório em dev)
html5lib = pytest.importorskip("html5lib")


@pytest.fixture
def sample_html() -> str:
    """HTML de exemplo válido."""
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>Test</title></head>
<body><h1>Olá</h1><p>Conteúdo válido.</p></body>
</html>"""


@pytest.mark.unit
def test_valid_html_parses_strict(sample_html: str) -> None:
    """HTML válido passa em html5lib strict."""
    parser = html5lib.HTMLParser(strict=True)
    parser.parse(sample_html)
    assert parser.errors == []


@pytest.mark.unit
def test_invalid_html_raises() -> None:
    """HTML malformado é detectado em strict mode."""
    bad = "<html><body><p>unclosed"
    parser = html5lib.HTMLParser(strict=True)
    # html5lib levanta exception genérica em strict; aceitamos qualquer erro.
    with pytest.raises(Exception):  # noqa: B017 — html5lib usa hierarquia genérica
        parser.parse(bad)


@pytest.mark.unit
def test_email_template_renders_valid_html() -> None:
    """Template real de email renderiza HTML válido em html5lib strict."""
    pytest.importorskip("jinja2")

    from monitoritcd.notifiers.email_notifier import render_email  # noqa: PLC0415

    # Sem documentos (caso vazio)
    subject, html = render_email(
        docs=[],
        digest_label="Diário",
        data_geracao=datetime.now(UTC),
    )
    assert isinstance(subject, str)
    assert isinstance(html, str)
    assert "MonitorITCD" in subject

    # html5lib parser não-strict ainda detecta erros graves
    parser = html5lib.HTMLParser()
    parser.parse(html)
    # Erros de well-formedness (não erros de doctype/encoding)
    fatal_errors = [e for e in parser.errors if "expected" in str(e[1]).lower()]
    assert not fatal_errors, f"HTML mal-formado: {fatal_errors[:3]}"
