"""Regressões do particionamento da suíte no CI."""

from pathlib import Path

import pytest
from scripts.ci_test_shards import (
    cargas_estimadas,
    descobrir_arquivos,
    descobrir_arquivos_tooling,
    particionar,
    validar_particoes,
)


@pytest.mark.unit
def test_particionamento_real_e_deterministico_sem_omissao_ou_duplicacao() -> None:
    """Cada arquivo real da aplicação pertence a exatamente um shard estável."""
    raiz = Path(__file__).parents[2]
    arquivos = descobrir_arquivos(raiz)

    primeira_execucao = particionar(arquivos, 3)
    segunda_execucao = particionar(tuple(reversed(arquivos)), 3)

    assert primeira_execucao == segunda_execucao
    validar_particoes(arquivos, primeira_execucao)
    assert sorted(arquivo for shard in primeira_execucao for arquivo in shard) == list(arquivos)


@pytest.mark.unit
def test_particionamento_rejeita_entrada_duplicada() -> None:
    """Duplicação na fonte falha antes de selecionar qualquer runner."""
    with pytest.raises(ValueError, match="duplicados"):
        particionar(("tests/unit/test_exemplo.py", "tests/unit/test_exemplo.py"), 3)


@pytest.mark.unit
def test_shards_reais_ficam_equilibrados_pelos_tempos_da_baseline() -> None:
    """O maior shard estimado não excede o menor em mais de um segundo."""
    raiz = Path(__file__).parents[2]
    cargas = cargas_estimadas(particionar(descobrir_arquivos(raiz), 3))

    assert max(cargas) - min(cargas) <= 1.0


@pytest.mark.unit
def test_tooling_fica_fora_da_suite_principal() -> None:
    """Tooling tem runner próprio e não contamina a coleta da aplicação."""
    raiz = Path(__file__).parents[2]
    aplicacao = set(descobrir_arquivos(raiz))
    tooling = set(descobrir_arquivos_tooling(raiz))

    assert tooling == {"tests/unit/test_ci_test_shards.py"}
    assert aplicacao.isdisjoint(tooling)
