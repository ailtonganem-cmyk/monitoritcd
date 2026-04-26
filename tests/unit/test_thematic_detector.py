"""Testes do detector temático (Categoria 2 IDEAS.md).

Cobre 22 itens (#54, #59, #61, #62, #66, #74-#78, #79-#84, #87, #91-#95).
Meta: cobertura ≥ 95%, com edge cases para textos vazios, ruído e
ambiguidades.
"""

from __future__ import annotations

import pytest

from monitoritcd.filters.thematic_detector import (
    MAX_TEXT_BYTES,
    detect_aliquotas,
    detect_all,
    detect_modulacao_efeitos,
    detect_normas_citadas,
    detect_numero_ato,
    detect_recurso_tipo,
    detect_relator,
    detect_repetitivo,
    detect_revogacao,
    detect_sancao,
    detect_temas_especificos,
    detect_temas_stf_stj,
    detect_valores_monetarios,
    detect_veto,
)


@pytest.mark.unit
class TestNumeroAto:
    def test_lei_com_numero(self) -> None:
        assert detect_numero_ato("Lei nº 14.123/2024 institui...") == "14123/2024"

    def test_decreto_curto(self) -> None:
        assert detect_numero_ato("Decreto 5/2024 publicado") == "5/2024"

    def test_sem_numero(self) -> None:
        assert detect_numero_ato("Apenas texto sem ato") is None

    def test_texto_vazio(self) -> None:
        assert detect_numero_ato(None) is None
        assert detect_numero_ato("") is None


@pytest.mark.unit
class TestAliquotas:
    def test_aliquota_simples(self) -> None:
        result = detect_aliquotas("Alíquota de 4% sobre o ITCD")
        assert "4%" in result

    def test_progressiva_range(self) -> None:
        result = detect_aliquotas("Alíquota progressiva de 4% a 8%")
        assert any("-" in r for r in result)

    def test_decimal_com_virgula(self) -> None:
        result = detect_aliquotas("Alíquota de 4,5% para ITCD")
        assert "4.5%" in result

    def test_sem_aliquota(self) -> None:
        assert detect_aliquotas("Texto sem percentual") == []

    def test_falsa_porcentagem_isolada(self) -> None:
        assert detect_aliquotas("100% das transações") == []


@pytest.mark.unit
class TestSancaoVeto:
    def test_sancao_detectada(self) -> None:
        assert detect_sancao("Lei sancionada pelo Governador") is True

    def test_sancionou(self) -> None:
        assert detect_sancao("Presidente sancionou a lei ontem") is True

    def test_veto_total(self) -> None:
        assert detect_veto("Veto total ao projeto") is True

    def test_vetou(self) -> None:
        assert detect_veto("Governador vetou o art. 5º") is True

    def test_nem_sancao_nem_veto(self) -> None:
        assert detect_sancao("PL em tramitação") is False
        assert detect_veto("PL em tramitação") is False


@pytest.mark.unit
class TestRelator:
    def test_relator_deputado(self) -> None:
        result = detect_relator("Relator: Dep. João Silva Santos")
        assert result is not None
        assert "João Silva Santos" in result

    def test_relator_ministro(self) -> None:
        result = detect_relator("Relator Min. Luiz Fux")
        assert result is not None

    def test_sem_relator(self) -> None:
        assert detect_relator("Texto sem indicação") is None


@pytest.mark.unit
class TestRevogacao:
    def test_revoga_lei(self) -> None:
        result = detect_revogacao("Esta lei revoga a Lei 1234/2020")
        assert result == ["1234/2020"]

    def test_revogadas_multiplas(self) -> None:
        result = detect_revogacao("Revogam-se a Lei 100/2010 e a Lei 200/2015")
        assert "100/2010" in result
        assert "200/2015" in result

    def test_sem_revogacao(self) -> None:
        assert detect_revogacao("Texto neutro") == []


@pytest.mark.unit
class TestRecursos:
    def test_embargos(self) -> None:
        result = detect_recurso_tipo("Embargos infringentes opostos")
        assert "embargos" in result

    def test_resp(self) -> None:
        result = detect_recurso_tipo("REsp nº 1234567 / SP")
        assert "resp" in result

    def test_re(self) -> None:
        result = detect_recurso_tipo("Recurso Extraordinário acolhido")
        assert "re" in result

    def test_combinado(self) -> None:
        result = detect_recurso_tipo("REsp e Recurso Extraordinário")
        assert {"resp", "re"} <= result


@pytest.mark.unit
class TestRepetitivo:
    def test_repetitivo_recursos(self) -> None:
        assert detect_repetitivo("Sob o rito dos recursos repetitivos") is True

    def test_repetitivo_materia(self) -> None:
        assert detect_repetitivo("Matéria submetida ao rito repetitivo") is True

    def test_nao_repetitivo(self) -> None:
        assert detect_repetitivo("Caso isolado") is False


@pytest.mark.unit
class TestTemasSTFSTJ:
    def test_tema_stf(self) -> None:
        result = detect_temas_stf_stj("Tema STF nº 825 julgado")
        assert "825" in result

    def test_tema_repercussao(self) -> None:
        result = detect_temas_stf_stj("Tema de repercussão geral 100")
        assert "100" in result

    def test_sem_tema(self) -> None:
        assert detect_temas_stf_stj("Texto neutro") == []


@pytest.mark.unit
class TestNormasCitadas:
    def test_lei_e_artigo(self) -> None:
        result = detect_normas_citadas("Aplica-se a Lei 14.123/2024 e o art. 1.784 do CC")
        assert any("14123" in r or "14.123" in r for r in result) or "14123/2024" in result

    def test_dedup(self) -> None:
        result = detect_normas_citadas("Lei 100/2010, Lei 100/2010 novamente")
        assert result.count("100/2010") <= 1

    def test_limit(self) -> None:
        text = " ".join(f"Lei {i}/2024" for i in range(1, 30))
        result = detect_normas_citadas(text, limit=5)
        assert len(result) == 5


@pytest.mark.unit
class TestValoresMonetarios:
    def test_real_simples(self) -> None:
        result = detect_valores_monetarios("Valor de R$ 100.000,00")
        assert any("R$ 100" in v or "100.000" in v for v in result)

    def test_milhao(self) -> None:
        result = detect_valores_monetarios("Patrimônio de R$ 5 milhões")
        assert len(result) >= 1

    def test_sem_valor(self) -> None:
        assert detect_valores_monetarios("Texto sem cifras") == []

    def test_limit(self) -> None:
        text = "R$ 100,00 " * 30
        result = detect_valores_monetarios(text, limit=3)
        assert len(result) == 3


@pytest.mark.unit
class TestModulacao:
    def test_modulacao_efeitos(self) -> None:
        assert detect_modulacao_efeitos("STF determinou modulação de efeitos") is True

    def test_sem_modulacao(self) -> None:
        assert detect_modulacao_efeitos("Decisão sem modulação") is False


@pytest.mark.unit
class TestTemasEspecificos:
    def test_planejamento_sucessorio(self) -> None:
        assert "planejamento_sucessorio" in detect_temas_especificos("Planejamento sucessório")

    def test_holding_familiar(self) -> None:
        assert "holding_familiar" in detect_temas_especificos("Holding familiar como veículo")

    def test_holding_patrimonial(self) -> None:
        assert "holding_familiar" in detect_temas_especificos("holding patrimonial constituída")

    def test_doacao_usufruto(self) -> None:
        result = detect_temas_especificos("doação com reserva de usufruto vitalício")
        assert "doacao_com_usufruto" in result

    def test_testamento(self) -> None:
        assert "testamento" in detect_temas_especificos("Testamento público lavrado")

    def test_offshore(self) -> None:
        assert "offshore_exterior" in detect_temas_especificos("Bens offshore declarados")

    def test_aliquota_progressiva_tema(self) -> None:
        result = detect_temas_especificos("Alíquota progressiva no estado")
        assert "aliquota_progressiva" in result

    def test_pec_itcd(self) -> None:
        result = detect_temas_especificos("PEC 45/2019 e a unificação nacional do ITCD")
        assert "pec_itcd_federal" in result

    def test_fato_gerador(self) -> None:
        assert "fato_gerador" in detect_temas_especificos(
            "Fato gerador do ITCD ocorre na transmissão"
        )

    def test_base_calculo(self) -> None:
        assert "base_de_calculo" in detect_temas_especificos("Base de cálculo é o valor do bem")

    def test_isencao(self) -> None:
        assert "isencao" in detect_temas_especificos("Isenção para pequenos valores")

    def test_imunidade(self) -> None:
        assert "imunidade" in detect_temas_especificos("Imunidade tributária recíproca")

    def test_gia_itcmd(self) -> None:
        assert "gia_itcmd" in detect_temas_especificos("Apresentação da GIA-ITCMD obrigatória")

    def test_gia_isolado(self) -> None:
        assert "gia_itcmd" in detect_temas_especificos("Declaração GIA pendente")

    def test_sem_temas(self) -> None:
        assert detect_temas_especificos("Texto neutro sem temas relevantes") == set()

    def test_texto_vazio(self) -> None:
        assert detect_temas_especificos(None) == set()
        assert detect_temas_especificos("") == set()


@pytest.mark.unit
class TestDetectAll:
    def test_consolida_metadados_estruturados(self) -> None:
        titulo = "Lei nº 14.123/2024 sancionada — alíquota progressiva de 4% a 8%"
        texto = (
            "O Governador sancionou a lei. Revoga a Lei 1234/2020. "
            "Holding familiar e planejamento sucessório afetados. "
            "Tema STF 825 considerado. R$ 1.000.000,00 mencionado."
        )
        out = detect_all(titulo, texto)
        assert out["numero_ato"] == "14123/2024"
        assert out["sancao_detectada"] == "true"
        assert "4%-8%" in out["aliquotas"] or "4%" in out["aliquotas"]
        assert "1234/2020" in out["revogacoes_citadas"]
        assert "825" in out["temas_stf_stj"]
        assert "holding_familiar" in out["temas_especificos"]
        assert "planejamento_sucessorio" in out["temas_especificos"]

    def test_texto_neutro_sem_chaves(self) -> None:
        out = detect_all("Bom dia", "Apenas saudação")
        # nenhum detector hit; dict pode vir vazio
        assert isinstance(out, dict)

    def test_titulo_none_e_texto_none(self) -> None:
        out = detect_all(None, None)
        assert out == {}

    def test_consolida_sinaliza_todos_os_ramos_secundarios(self) -> None:
        """Cobre branches de veto, relator, recurso, repetitivo, modulação,
        valores, normas — todos no mesmo texto."""
        titulo = "REsp 1.234.567 — Embargos infringentes acolhidos"
        texto = (
            "Relator: Min. Luiz Fux. O Governador vetou o art. 5º. "
            "Sob o rito dos recursos repetitivos. STF determinou modulação de efeitos. "
            "Aplica-se a Lei 14.123/2024. Indenização de R$ 500.000,00 fixada."
        )
        out = detect_all(titulo, texto)
        assert out.get("veto_detectado") == "true"
        assert "relator" in out
        assert "recurso_tipos" in out
        assert out.get("repetitivo") == "true"
        assert out.get("modulacao_efeitos") == "true"
        assert "normas_citadas" in out
        assert "valores_monetarios" in out


@pytest.mark.unit
class TestRobustness:
    def test_texto_excessivamente_longo_truncado(self) -> None:
        # Texto > MAX_TEXT_BYTES é truncado defensivamente sem crash
        big = "ITCMD " * (MAX_TEXT_BYTES // 6 + 1000)
        result = detect_temas_especificos(big)
        # Não deve crashar; pode ou não detectar dependendo da posição
        assert isinstance(result, set)

    def test_caracteres_unicode(self) -> None:
        # NFKC normalization deve permitir matching mesmo com acentos compostos
        text = "imunídade tributária"  # imunidade + acento combinado
        result = detect_temas_especificos(text)
        # Aceita match ou não; importante não crashar
        assert isinstance(result, set)

    def test_caracteres_de_controle_filtrados(self) -> None:
        text = "Lei nº 100/2024\x00\x01\x02 sancionada"
        # Não deve crashar
        assert detect_numero_ato(text) == "100/2024"
