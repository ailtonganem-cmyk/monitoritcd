#!/usr/bin/env python3
# ruff: noqa: E501
# Justificativa: o template HTML/CSS embutido neste script tem linhas longas
# inerentes a CSS one-line; quebrar artificialmente reduziria legibilidade.
"""Gera dashboard estático em HTML para GitHub Pages.

Uso:
    python scripts/build_dashboard.py --output docs/dashboard/index.html

Em CI: chamado por workflow `pages.yml` após cada cron.
Lê dados do Firestore se disponível, senão gera dashboard "vazio" com
template padrão.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _load_configured_sources() -> list[dict[str, Any]]:
    """Lê YAMLs de fontes ativas (ativo: true) em sources/.

    Retorna lista de {id, uf, nome} para cruzar com docs coletados.
    """
    import yaml  # noqa: PLC0415

    repo_root = Path(__file__).resolve().parent.parent
    sources_dir = repo_root / "sources"
    if not sources_dir.is_dir():
        return []

    configured = []
    for yaml_path in sorted(sources_dir.rglob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("ativo") is True:
                configured.append(
                    {
                        "id": data.get("id", yaml_path.stem),
                        "uf": data.get("uf", "?"),
                        "nome": data.get("nome", data.get("id", "")),
                    }
                )
        except (yaml.YAMLError, OSError) as e:
            print(f"AVISO: falha ao ler {yaml_path}: {e}", file=sys.stderr)
    return configured


def _source_health(
    rows: list[dict[str, Any]], configured: list[dict[str, Any]], now: datetime
) -> list[dict[str, Any]]:
    """Cruza fontes configuradas com docs reais para diagnosticar fontes silenciosas."""
    by_source_count: Counter[str] = Counter()
    by_source_last: dict[str, datetime] = {}

    for r in rows:
        source_id = r.get("source", {}).get("id")
        if not source_id:
            continue
        by_source_count[source_id] += 1
        fetched_str = r.get("original", {}).get("fetched_at")
        if fetched_str:
            try:
                ts = datetime.fromisoformat(str(fetched_str).replace("Z", "+00:00"))
                if source_id not in by_source_last or ts > by_source_last[source_id]:
                    by_source_last[source_id] = ts
            except (ValueError, TypeError):
                continue

    health = []
    for src in configured:
        last = by_source_last.get(src["id"])
        days_ago = (now - last).days if last else None
        # Fonte silenciosa: configurada mas sem doc nos últimos 7 dias
        silent = days_ago is None or days_ago > 7  # noqa: PLR2004
        health.append(
            {
                "id": src["id"],
                "uf": src["uf"],
                "nome": src["nome"],
                "docs_total": by_source_count.get(src["id"], 0),
                "last_seen_days": days_ago,
                "silent": silent,
            }
        )
    # Silenciosas primeiro (alerta), depois por contagem desc
    health.sort(key=lambda h: (not h["silent"], -h["docs_total"]))
    return health


def load_metrics() -> dict[str, Any]:
    """Carrega métricas do Firestore. Fallback: dict vazio."""
    try:
        from google.cloud.firestore import Client  # noqa: PLC0415

        client = Client()
        owner_id = __import__("os").environ.get("OWNER_ID", "")

        query = (
            client.collection("monitor_documentos")
            .where("owner_id", "==", owner_id)
            .order_by("original.fetched_at", direction="DESCENDING")
            .limit(500)
        )
        docs = list(query.stream())
        rows = [d.to_dict() for d in docs]
    except Exception as e:
        print(f"AVISO: Firestore indisponível ({e}). Gerando dashboard vazio.", file=sys.stderr)
        rows = []

    now = datetime.now(UTC)

    by_uf = Counter(r.get("source", {}).get("uf", "?") for r in rows)
    by_topic: Counter[str] = Counter()
    for r in rows:
        for t in (r.get("llm") or {}).get("topics", []):
            by_topic[t] += 1
    by_severity = Counter((r.get("llm") or {}).get("severity_tier", "n/a") for r in rows)

    last_7d = sum(
        1
        for r in rows
        if r.get("original", {}).get("fetched_at")
        and (
            now - datetime.fromisoformat(str(r["original"]["fetched_at"]).replace("Z", "+00:00"))
        ).days
        <= 7  # noqa: PLR2004
    )

    # Cruzar fontes configuradas com docs coletados (health check)
    configured = _load_configured_sources()
    sources_health = _source_health(rows, configured, now)
    silent_count = sum(1 for h in sources_health if h["silent"])

    # Hit rate por UF nos últimos 7 dias (E3: ajuda a ver onde fontes funcionam)
    by_uf_7d: Counter[str] = Counter()
    for r in rows:
        fetched_str = r.get("original", {}).get("fetched_at")
        if not fetched_str:
            continue
        try:
            ts = datetime.fromisoformat(str(fetched_str).replace("Z", "+00:00"))
            if (now - ts).days <= 7:  # noqa: PLR2004
                by_uf_7d[r.get("source", {}).get("uf", "?")] += 1
        except (ValueError, TypeError):
            continue

    return {
        "generated_at": now.isoformat(),
        "total": len(rows),
        "last_7d": last_7d,
        "configured_sources": len(configured),
        "silent_sources": silent_count,
        "by_uf": dict(by_uf.most_common()),
        "by_uf_7d": dict(by_uf_7d.most_common()),
        "by_topic": dict(by_topic.most_common()),
        "by_severity": dict(by_severity.most_common()),
        "sources_health": sources_health,
        "recent": [
            {
                "doc_id": r.get("doc_id"),
                "titulo": r.get("original", {}).get("titulo_raw", "")[:120],
                "uf": r.get("source", {}).get("uf"),
                "tier": (r.get("llm") or {}).get("severity_tier"),
                "url": r.get("original", {}).get("url"),
            }
            for r in rows[:20]
        ],
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>MonitorITCD - Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root {
  --bg: #0d1117;
  --fg: #c9d1d9;
  --card: #161b22;
  --border: #30363d;
  --accent: #58a6ff;
  --critico: #f85149;
  --alta: #d29922;
  --normal: #1f6feb;
  --baixa: #3fb950;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 24px; }
.container { max-width: 1100px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px 0; }
.subtitle { color: #8b949e; font-size: 13px; margin-bottom: 24px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.metric { font-size: 32px; font-weight: 600; }
.label { color: #8b949e; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
.section { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.section h2 { font-size: 14px; margin: 0 0 12px 0; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
.bar-chart { display: flex; flex-direction: column; gap: 6px; }
.bar-row { display: grid; grid-template-columns: 110px 1fr 50px; gap: 8px; align-items: center; font-size: 13px; }
.bar { background: var(--border); height: 16px; border-radius: 3px; position: relative; overflow: hidden; }
.bar-fill { background: var(--accent); height: 100%; border-radius: 3px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--border); }
th { color: #8b949e; font-weight: 500; font-size: 11px; text-transform: uppercase; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.tier-critico { color: var(--critico); font-weight: 600; }
.tier-alta { color: var(--alta); font-weight: 600; }
.tier-normal { color: var(--normal); }
.tier-baixa { color: var(--baixa); }
.silent { color: var(--critico); }
.healthy { color: var(--baixa); }
.empty { text-align: center; color: #8b949e; padding: 32px; }
footer { color: #8b949e; font-size: 11px; text-align: center; margin-top: 24px; }
</style>
</head>
<body>
<div class="container">
  <h1>MonitorITCD - Dashboard</h1>
  <div class="subtitle">Gerado em <span id="ts">$GENERATED_AT$</span></div>

  <div class="cards">
    <div class="card"><div class="label">Total armazenado</div><div class="metric">$TOTAL$</div></div>
    <div class="card"><div class="label">Ultimos 7 dias</div><div class="metric">$LAST7D$</div></div>
    <div class="card"><div class="label">Fontes config.</div><div class="metric">$CONFIGURED$</div></div>
    <div class="card"><div class="label">Silenciosas (>7d)</div><div class="metric silent">$SILENT$</div></div>
  </div>

  <div class="section">
    <h2>Hit rate por UF (7 dias)</h2>
    <div class="bar-chart" id="by-uf-7d">$BY_UF_7D$</div>
  </div>

  <div class="section">
    <h2>Distribuicao por UF (total)</h2>
    <div class="bar-chart" id="by-uf">$BY_UF$</div>
  </div>

  <div class="section">
    <h2>Por topico</h2>
    <div class="bar-chart" id="by-topic">$BY_TOPIC$</div>
  </div>

  <div class="section">
    <h2>Severity tiers</h2>
    <div class="bar-chart" id="by-severity">$BY_SEVERITY$</div>
  </div>

  <div class="section">
    <h2>Saude das fontes (configuradas vs coletadas)</h2>
    $SOURCES_HEALTH$
  </div>

  <div class="section">
    <h2>Recentes (20)</h2>
    $RECENT_TABLE$
  </div>

  <footer>
    MonitorITCD &middot; Sistema pessoal de monitoramento ITCD/Sucessoes/Regime de Bens<br>
    <a href="https://github.com/ailtonganem-cmyk/monitoritcd">github</a> &middot;
    dados via Firestore (owner-scoped)
  </footer>
</div>
</body>
</html>
"""


def _bar_chart(data: dict[str, int], max_value: int) -> str:
    if not data:
        return '<div class="empty">Sem dados</div>'
    rows = []
    for label, count in data.items():
        pct = int(100 * count / max_value) if max_value else 0
        rows.append(
            f'<div class="bar-row">'
            f"<div>{label}</div>"
            f'<div class="bar"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f"<div>{count}</div>"
            f"</div>"
        )
    return "\n".join(rows)


def _recent_table(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<div class="empty">Nenhum documento ainda. Aguardando primeiro cron.</div>'
    rows = []
    for it in items:
        tier = it.get("tier", "n/a")
        rows.append(
            f"<tr>"
            f'<td><span class="tier-{tier}">{tier}</span></td>'
            f"<td>{it.get('uf', '?')}</td>"
            f'<td><a href="{it.get("url", "#")}" target="_blank" rel="noopener">{it["titulo"]}</a></td>'
            f"</tr>"
        )
    return "<table><tr><th>Tier</th><th>UF</th><th>Titulo</th></tr>" + "".join(rows) + "</table>"


def _sources_health_table(health: list[dict[str, Any]]) -> str:
    if not health:
        return '<div class="empty">Nenhuma fonte ativa configurada.</div>'
    rows = []
    for h in health:
        last = h["last_seen_days"]
        if last is None:
            last_str = '<span class="silent">nunca</span>'
        elif h["silent"]:
            last_str = f'<span class="silent">{last}d</span>'
        else:
            last_str = f'<span class="healthy">{last}d</span>'
        status = "🔴" if h["silent"] else "🟢"
        rows.append(
            f"<tr>"
            f"<td>{status}</td>"
            f"<td>{h['uf']}</td>"
            f"<td>{h['nome']}</td>"
            f"<td>{h['docs_total']}</td>"
            f"<td>{last_str}</td>"
            f"</tr>"
        )
    return (
        "<table><tr><th></th><th>UF</th><th>Fonte</th><th>Docs</th><th>Última</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def render_html(metrics: dict[str, Any]) -> str:
    by_uf = metrics["by_uf"]
    by_uf_7d = metrics["by_uf_7d"]
    by_topic = metrics["by_topic"]
    by_severity = metrics["by_severity"]
    max_uf = max(by_uf.values(), default=1)
    max_uf_7d = max(by_uf_7d.values(), default=1)
    max_topic = max(by_topic.values(), default=1)
    max_sev = max(by_severity.values(), default=1)

    return (
        HTML_TEMPLATE.replace("$GENERATED_AT$", metrics["generated_at"])
        .replace("$TOTAL$", str(metrics["total"]))
        .replace("$LAST7D$", str(metrics["last_7d"]))
        .replace("$CONFIGURED$", str(metrics["configured_sources"]))
        .replace("$SILENT$", str(metrics["silent_sources"]))
        .replace("$BY_UF$", _bar_chart(by_uf, max_uf))
        .replace("$BY_UF_7D$", _bar_chart(by_uf_7d, max_uf_7d))
        .replace("$BY_TOPIC$", _bar_chart(by_topic, max_topic))
        .replace("$BY_SEVERITY$", _bar_chart(by_severity, max_sev))
        .replace("$SOURCES_HEALTH$", _sources_health_table(metrics["sources_health"]))
        .replace("$RECENT_TABLE$", _recent_table(metrics["recent"]))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/dashboard/index.html")
    parser.add_argument("--metrics-json", default=None, help="Salvar metricas raw em JSON")
    args = parser.parse_args()

    metrics = load_metrics()
    html = render_html(metrics)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard escrito: {out} ({len(html)} bytes)")

    if args.metrics_json:
        Path(args.metrics_json).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Metricas JSON: {args.metrics_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
