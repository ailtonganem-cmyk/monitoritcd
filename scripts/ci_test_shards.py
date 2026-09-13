"""Distribui arquivos de teste entre shards determinísticos do CI.

Os pesos abaixo vieram do JUnit da suíte integral no SHA
846b3bfd79174f69527e32e3910393e9069d8574. O particionamento usa LPT
(maior duração primeiro) e desempate lexical, portanto todas as versões de
Python calculam exatamente a mesma distribuição.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

PESO_PADRAO_SEGUNDOS = 0.05
ARQUIVOS_TOOLING = frozenset({"tests/unit/test_ci_test_shards.py"})

# Duração agregada dos casos de cada arquivo na baseline. Arquivos novos usam
# PESO_PADRAO_SEGUNDOS até a próxima medição, sem risco de omissão.
PESOS_SEGUNDOS: dict[str, float] = {
    "tests/e2e/test_smoke_pipeline.py": 0.021,
    "tests/integration/test_alep.py": 0.120,
    "tests/integration/test_alepe.py": 16.566,
    "tests/integration/test_bot_handlers.py": 1.727,
    "tests/integration/test_bot_watch.py": 0.042,
    "tests/integration/test_camara_deputados.py": 4.090,
    "tests/integration/test_collectors.py": 10.685,
    "tests/integration/test_iof_mg.py": 0.143,
    "tests/integration/test_lexml_portal.py": 6.307,
    "tests/integration/test_orchestrator.py": 42.270,
    "tests/integration/test_orchestrator_digest.py": 5.204,
    "tests/integration/test_orchestrator_error_paths.py": 10.040,
    "tests/integration/test_orchestrator_notify_reprocess.py": 0.289,
    "tests/integration/test_orchestrator_source_run_health.py": 0.200,
    "tests/integration/test_sapl.py": 4.101,
    "tests/integration/test_senado.py": 0.083,
    "tests/llm_regression/test_prompt_version.py": 0.006,
    "tests/security/input_validation/test_bot_commands.py": 2.453,
    "tests/security/input_validation/test_url_fuzz.py": 0.078,
    "tests/security/input_validation/test_yaml_loader_fuzz.py": 0.049,
    "tests/security/sanitization/test_html_sanitization.py": 0.216,
    "tests/security/ssrf/test_url_validator.py": 0.117,
    "tests/security/test_log_redactor.py": 0.251,
    "tests/security/test_markdown_escape.py": 0.185,
    "tests/security/test_pentest_fixes.py": 0.018,
    "tests/templates/test_email_render.py": 0.204,
    "tests/templates/test_telegram_render.py": 0.105,
    "tests/unit/test_analytics.py": 0.016,
    "tests/unit/test_base_collector.py": 44.547,
    "tests/unit/test_bot_audit.py": 0.021,
    "tests/unit/test_bot_auth.py": 0.019,
    "tests/unit/test_bot_handlers_extra.py": 0.417,
    "tests/unit/test_bot_poller.py": 1.453,
    "tests/unit/test_build_dashboard.py": 0.252,
    "tests/unit/test_citation_validator.py": 0.015,
    "tests/unit/test_cleanup_retention.py": 0.005,
    "tests/unit/test_config.py": 0.068,
    "tests/unit/test_dedup.py": 0.023,
    "tests/unit/test_email_notifier.py": 0.231,
    "tests/unit/test_extractors.py": 0.016,
    "tests/unit/test_feeds.py": 0.012,
    "tests/unit/test_firestore_schema_snapshot.py": 0.004,
    "tests/unit/test_firestore_store.py": 0.013,
    "tests/unit/test_groq.py": 0.037,
    "tests/unit/test_html_validation.py": 0.050,
    "tests/unit/test_iof_mg_collector.py": 0.074,
    "tests/unit/test_keywords.py": 0.135,
    "tests/unit/test_limits.py": 0.009,
    "tests/unit/test_llm_classifier.py": 18.059,
    "tests/unit/test_llm_fallback.py": 0.016,
    "tests/unit/test_metrics.py": 0.012,
    "tests/unit/test_models.py": 0.037,
    "tests/unit/test_multi_channel.py": 4.081,
    "tests/unit/test_observability.py": 0.014,
    "tests/unit/test_orchestrator_audit_chain.py": 0.009,
    "tests/unit/test_orchestrator_filter_keywords.py": 0.011,
    "tests/unit/test_per_command_rate_limit.py": 0.007,
    "tests/unit/test_prepare_bot_webhook_source.py": 0.014,
    "tests/unit/test_prescore.py": 0.012,
    "tests/unit/test_reconcile_owner.py": 0.014,
    "tests/unit/test_resilience.py": 0.023,
    "tests/unit/test_sanitize.py": 0.222,
    "tests/unit/test_search.py": 0.045,
    "tests/unit/test_search_extra.py": 0.009,
    "tests/unit/test_security_pii_injection.py": 0.022,
    "tests/unit/test_severity.py": 0.025,
    "tests/unit/test_severity_override.py": 0.011,
    "tests/unit/test_source_health.py": 0.020,
    "tests/unit/test_source_loader.py": 0.332,
    "tests/unit/test_source_validators_extra.py": 0.008,
    "tests/unit/test_storage_inmemory.py": 0.067,
    "tests/unit/test_telegram_actions.py": 0.014,
    "tests/unit/test_telegram_notifier.py": 4.298,
    "tests/unit/test_thematic_cluster.py": 0.005,
    "tests/unit/test_thematic_detector.py": 0.320,
    "tests/unit/test_timeout_enforcement.py": 0.105,
    "tests/unit/test_watches.py": 0.047,
}


def descobrir_arquivos(raiz: Path) -> tuple[str, ...]:
    """Descobre todos os arquivos de teste que pertencem à suíte principal."""
    return tuple(
        sorted(
            relativo
            for caminho in (raiz / "tests").rglob("test_*.py")
            if caminho.is_file()
            if (relativo := caminho.relative_to(raiz).as_posix()) not in ARQUIVOS_TOOLING
        )
    )


def descobrir_arquivos_tooling(raiz: Path) -> tuple[str, ...]:
    """Descobre testes do tooling, executados fora da suíte da aplicação."""
    return tuple(sorted(arquivo for arquivo in ARQUIVOS_TOOLING if (raiz / arquivo).is_file()))


def particionar(arquivos: tuple[str, ...], total_shards: int) -> tuple[tuple[str, ...], ...]:
    """Particiona por LPT com desempate estável por caminho e índice do shard."""
    if total_shards < 1:
        raise ValueError("O total de shards deve ser positivo.")
    if len(arquivos) != len(set(arquivos)):
        raise ValueError("A entrada contém arquivos duplicados.")

    particoes: list[list[str]] = [[] for _ in range(total_shards)]
    cargas = [0.0] * total_shards
    ordenados = sorted(
        arquivos,
        key=lambda arquivo: (-PESOS_SEGUNDOS.get(arquivo, PESO_PADRAO_SEGUNDOS), arquivo),
    )

    for arquivo in ordenados:
        indice = min(range(total_shards), key=lambda atual: (cargas[atual], atual))
        particoes[indice].append(arquivo)
        cargas[indice] += PESOS_SEGUNDOS.get(arquivo, PESO_PADRAO_SEGUNDOS)

    resultado = tuple(tuple(sorted(particao)) for particao in particoes)
    validar_particoes(arquivos, resultado)
    return resultado


def validar_particoes(arquivos: tuple[str, ...], particoes: tuple[tuple[str, ...], ...]) -> None:
    """Falha diante de omissão, duplicação ou arquivo estranho."""
    esperados = Counter(arquivos)
    encontrados = Counter(arquivo for particao in particoes for arquivo in particao)
    if encontrados != esperados:
        omitidos = sorted((esperados - encontrados).elements())
        duplicados = sorted(
            arquivo for arquivo, quantidade in encontrados.items() if quantidade > 1
        )
        estranhos = sorted((encontrados - esperados).elements())
        raise ValueError(
            f"Particionamento inválido: omitidos={omitidos}, "
            f"duplicados={duplicados}, estranhos={estranhos}"
        )


def cargas_estimadas(particoes: tuple[tuple[str, ...], ...]) -> tuple[float, ...]:
    """Retorna a carga histórica estimada de cada shard em segundos."""
    return tuple(
        round(
            sum(PESOS_SEGUNDOS.get(arquivo, PESO_PADRAO_SEGUNDOS) for arquivo in particao),
            3,
        )
        for particao in particoes
    )


def main() -> int:
    """Expõe a seleção de shard e um resumo verificável para o workflow."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--raiz", type=Path, default=Path.cwd())
    parser.add_argument("--total", type=int, default=3)
    parser.add_argument("--indice", type=int)
    parser.add_argument("--resumo", action="store_true")
    argumentos = parser.parse_args()

    arquivos = descobrir_arquivos(argumentos.raiz)
    particoes = particionar(arquivos, argumentos.total)
    if argumentos.resumo:
        print(
            json.dumps(
                {
                    "arquivos": len(arquivos),
                    "cargas_estimadas_segundos": cargas_estimadas(particoes),
                    "quantidades": tuple(len(particao) for particao in particoes),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    if argumentos.indice is None or not 1 <= argumentos.indice <= argumentos.total:
        parser.error("--indice deve estar entre 1 e --total")
    print("\n".join(particoes[argumentos.indice - 1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
