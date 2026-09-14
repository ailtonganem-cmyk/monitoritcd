"""Deploy runtime Firebase (Functions + Scheduler + Hosting). Não imprime secrets."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

PROJETO = "monitoritcd"
REGIAO = "southamerica-east1"
APIS = Path.home() / "Projetos" / "APIs"


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> str:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    out = subprocess.run(cmd, check=True, capture_output=True, text=True, env=merged)
    return out.stdout


def _env_bot_webhook() -> dict[str, str]:
    raw = _run(
        [
            "gcloud",
            "functions",
            "describe",
            "bot_webhook",
            f"--project={PROJETO}",
            f"--region={REGIAO}",
            "--gen2",
            "--format=json",
        ]
    )
    dados = json.loads(raw)
    svc = dados.get("serviceConfig") or {}
    env = dict(svc.get("environmentVariables") or {})
    env.pop("LOG_EXECUTION_ID", None)
    return {str(k): str(v) for k, v in env.items() if str(v).strip()}


def _ler_chave_arquivo(nome: str) -> str | None:
    path = APIS / nome
    if not path.is_file():
        return None
    linhas = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    return linhas[0] if linhas else None


def _novas_chaves(existentes: dict[str, str]) -> dict[str, str]:
    """Só adiciona o que ainda não está nas env da Function já publicada."""
    pares = (
        ("OPENROUTER", "openrouter.txt"),
        ("DEEPSEEK", "deepseek.txt"),
        ("OPENCODE", "opencode.txt"),
    )
    extra: dict[str, str] = {}
    for prefixo, arquivo in pares:
        env_nome = f"{prefixo}_API_KEY"
        if env_nome in existentes and existentes[env_nome].strip():
            continue
        valor = _ler_chave_arquivo(arquivo)
        if valor:
            extra[env_nome] = valor
    return extra


def _csv_env(env: dict[str, str]) -> str:
    partes = []
    for k, v in env.items():
        if "," in v or "\n" in v:
            raise ValueError(f"valor de {k} incompatível com --set-env-vars")
        partes.append(f"{k}={v}")
    return ",".join(partes)


def _preparar(fn: str, staging: Path) -> Path:
    raiz = Path(__file__).resolve().parents[1]
    dest = staging / fn
    _run(
        [
            "python3",
            str(raiz / "scripts" / "prepare_firebase_fn.py"),
            "--fn",
            fn,
            "--output",
            str(dest),
        ]
    )
    return dest


def _deploy_fn(nome: str, fonte: Path, env: dict[str, str], *, memoria: str, timeout: str) -> str:
    env = dict(env)
    env.setdefault("ENV", "production")
    env.setdefault("PAINEL_STORE", "firestore")
    env.setdefault("MONITORITCD_ROOT", "/workspace")
    env.setdefault("FIREBASE_PROJECT_ID", PROJETO)
    cmd = [
        "gcloud",
        "functions",
        "deploy",
        nome,
        "--gen2",
        "--runtime=python311",
        f"--region={REGIAO}",
        f"--source={fonte}",
        f"--entry-point={nome}",
        "--trigger-http",
        "--allow-unauthenticated",
        f"--memory={memoria}",
        f"--timeout={timeout}",
        "--max-instances=3",
        f"--set-env-vars={_csv_env(env)}",
        f"--project={PROJETO}",
        "--quiet",
    ]
    _run(cmd)
    desc = json.loads(
        _run(
            [
                "gcloud",
                "functions",
                "describe",
                nome,
                f"--project={PROJETO}",
                f"--region={REGIAO}",
                "--gen2",
                "--format=json",
            ]
        )
    )
    url = ((desc.get("serviceConfig") or {}).get("uri")) or ""
    if not url:
        raise RuntimeError(f"Function {nome} sem URL")
    return str(url)


def _scheduler(nome: str, schedule: str, url: str, token: str) -> None:
    comum = [
        f"--project={PROJETO}",
        f"--location={REGIAO}",
        f"--schedule={schedule}",
        "--time-zone=UTC",
        f"--uri={url}",
        "--http-method=POST",
        f"--headers=X-Cron-Token={token},Content-Type=application/json",
        "--attempt-deadline=1800s",
        "--quiet",
    ]
    try:
        _run(
            [
                "gcloud",
                "scheduler",
                "jobs",
                "describe",
                nome,
                f"--location={REGIAO}",
                f"--project={PROJETO}",
            ]
        )
        _run(["gcloud", "scheduler", "jobs", "update", "http", nome, *comum])
    except subprocess.CalledProcessError:
        _run(["gcloud", "scheduler", "jobs", "create", "http", nome, *comum])


def main() -> None:
    existentes = _env_bot_webhook()
    extra = _novas_chaves(existentes)
    token = existentes.get("MONITOR_CRON_TOKEN") or secrets.token_urlsafe(32)
    sessao = existentes.get("PAINEL_SESSION_SECRET") or secrets.token_urlsafe(32)
    oauth = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    if not oauth:
        env_local = Path(__file__).resolve().parents[1] / ".env"
        if env_local.is_file():
            for linha in env_local.read_text(encoding="utf-8").splitlines():
                if linha.startswith("GOOGLE_OAUTH_CLIENT_ID="):
                    oauth = linha.split("=", 1)[1].strip().strip('"')
                    break
    env = dict(existentes)
    env.update(extra)
    env["MONITOR_CRON_TOKEN"] = token
    env["PAINEL_SESSION_SECRET"] = sessao
    if oauth:
        env["GOOGLE_OAUTH_CLIENT_ID"] = oauth

    with tempfile.TemporaryDirectory(prefix="mitcd-fn-") as tmp:
        staging = Path(tmp)
        src_cron = _preparar("monitor_cron", staging)
        url_cron = _deploy_fn("monitor_cron", src_cron, env, memoria="2048MB", timeout="1800s")
        env["MONITOR_CRON_URL"] = url_cron
        src_painel = _preparar("painel_api", staging)
        url_painel = _deploy_fn("painel_api", src_painel, env, memoria="512MB", timeout="60s")

    _scheduler("monitor-cron-0233", "33 2 * * *", url_cron, token)
    _scheduler("monitor-cron-1013", "13 10 * * *", url_cron, token)
    _scheduler("monitor-cron-1447", "47 14 * * *", url_cron, token)

    print("monitor_cron:", url_cron)
    print("painel_api:", url_painel)
    print("chaves_novas:", ",".join(sorted(extra.keys())) or "(nenhuma)")
    print("oauth_client_id_configurado:", bool(oauth))


if __name__ == "__main__":
    main()
