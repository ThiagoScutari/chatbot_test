"""HTML and JSON report generator for FlowTest results."""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .models import FlowTestResult


CHART_JS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4"

# Region mapping for the per-persona summary table
PERSONA_REGIONS = {
    "dona_raimunda": "Norte (PA)",
    "seu_carlos": "Sul (RS)",
    "jessica": "Sudeste (SP)",
    "tiago": "Nordeste (BA)",
    "dona_maria": "Centro-Oeste (GO)",
}


def _persona_label(name: str) -> str:
    return name.replace("_", " ").title()


def _flow_label(name: str) -> str:
    return name.replace("_", " ").title()


def _truncate(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _row_class(turn_intent: str | None, latency_ms: int) -> str:
    if turn_intent is None:
        return "row-no-intent"
    if latency_ms > 3000:
        return "row-slow"
    return ""


def _completion_badge(rate: float) -> str:
    if rate >= 80:
        return "value-good"
    if rate >= 60:
        return "value-warn"
    return "value-bad"


def _build_summary(results: list[FlowTestResult]) -> dict[str, Any]:
    total = len(results)
    completed = sum(1 for r in results if r.completed)
    completion_rate = (completed / total * 100) if total else 0.0

    total_turns = sum(r.total_turns for r in results)
    avg_turns = (total_turns / total) if total else 0.0

    total_latency_ms = sum(r.total_latency_ms for r in results)
    avg_latency_per_turn_ms = (
        total_latency_ms / total_turns if total_turns else 0.0
    )

    return {
        "total": total,
        "completed": completed,
        "completion_rate": completion_rate,
        "total_turns": total_turns,
        "avg_turns": avg_turns,
        "avg_latency_per_turn_s": avg_latency_per_turn_ms / 1000.0,
    }


def _build_persona_stats(
    results: list[FlowTestResult],
) -> list[dict[str, Any]]:
    by_persona: dict[str, list[FlowTestResult]] = defaultdict(list)
    for r in results:
        by_persona[r.persona].append(r)

    stats: list[dict[str, Any]] = []
    for persona, items in sorted(by_persona.items()):
        n = len(items)
        avg_turns = sum(i.total_turns for i in items) / n
        completed = sum(1 for i in items if i.completed)
        completion_rate = completed / n * 100
        total_turns = sum(i.total_turns for i in items)
        total_lat = sum(i.total_latency_ms for i in items)
        avg_lat_turn = (total_lat / total_turns) if total_turns else 0.0
        stats.append({
            "persona": persona,
            "label": _persona_label(persona),
            "region": PERSONA_REGIONS.get(persona, "—"),
            "interactions": n,
            "avg_turns": avg_turns,
            "completed": completed,
            "completion_rate": completion_rate,
            "avg_latency_s": avg_lat_turn / 1000.0,
        })
    return stats


def _build_flow_stats(
    results: list[FlowTestResult],
    flows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    total = len(results)
    counts = Counter(r.flow for r in results)

    flow_meta = {f["name"]: f for f in flows}
    weight_total = sum(f["weight"] for f in flows) or 1

    stats: list[dict[str, Any]] = []
    for f in flows:
        name = f["name"]
        flow_results = [r for r in results if r.flow == name]
        n = counts.get(name, 0)
        expected_pct = f["weight"] / weight_total * 100
        actual_pct = (n / total * 100) if total else 0.0
        avg_turns = (
            sum(r.total_turns for r in flow_results) / n if n else 0.0
        )
        completed = sum(1 for r in flow_results if r.completed)
        completion_rate = (completed / n * 100) if n else 0.0
        stats.append({
            "flow": name,
            "label": _flow_label(name),
            "occurrences": n,
            "expected_weight_pct": expected_pct,
            "actual_pct": actual_pct,
            "avg_turns": avg_turns,
            "completed": completed,
            "completion_rate": completion_rate,
            "weight": f["weight"],
            "_meta_max_turns": flow_meta[name]["max_turns"],
        })
    return stats


def _render_conversation(idx: int, result: FlowTestResult) -> str:
    icon = "✅" if result.completed else "⚠️"
    summary = (
        f"#{idx + 1:02d} — {_persona_label(result.persona)} × "
        f"{_flow_label(result.flow)} — {icon} "
        f"{result.total_turns} turnos — "
        f"{result.total_latency_ms / 1000.0:.1f}s"
    )

    rows = []
    for turn in result.turns:
        cls = _row_class(turn.intent, turn.latency_ms)
        bot_full = html.escape(turn.bot_response or "")
        bot_short = html.escape(_truncate(turn.bot_response or "", 200))
        intent = html.escape(turn.intent or "—")
        rows.append(
            f"<tr class='{cls}'>"
            f"<td class='num'>{turn.number}</td>"
            f"<td class='client'>{html.escape(turn.client_message)}</td>"
            f"<td class='bot' title='{bot_full}'>{bot_short}</td>"
            f"<td class='intent'>{intent}</td>"
            f"<td class='lat'>{turn.latency_ms}</td>"
            f"</tr>"
        )

    return (
        f"<details>"
        f"<summary>{html.escape(summary)}</summary>"
        f"<table class='turns-table'>"
        f"<thead><tr>"
        f"<th>#</th><th>Cliente</th><th>Bot</th><th>Intent</th><th>ms</th>"
        f"</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table>"
        f"</details>"
    )


def _render_html(
    results: list[FlowTestResult],
    flows: list[dict[str, Any]],
    today: str,
    seed: int | None,
) -> str:
    summary = _build_summary(results)
    persona_stats = _build_persona_stats(results)
    flow_stats = _build_flow_stats(results, flows)

    persona_count = len({r.persona for r in results})
    seed_str = str(seed) if seed is not None else "—"

    # ── Charts ─────────────────────────────────────────────────────────────
    flow_dist_data = json.dumps({
        "labels": [s["label"] for s in flow_stats],
        "expected": [round(s["expected_weight_pct"], 1) for s in flow_stats],
        "actual": [round(s["actual_pct"], 1) for s in flow_stats],
    })

    flow_turns_sorted = sorted(
        flow_stats, key=lambda s: s["avg_turns"], reverse=True
    )
    flow_turns_data = json.dumps({
        "labels": [s["label"] for s in flow_turns_sorted],
        "values": [round(s["avg_turns"], 1) for s in flow_turns_sorted],
    })

    # ── Persona table ──────────────────────────────────────────────────────
    persona_rows = []
    for s in persona_stats:
        persona_rows.append(
            f"<tr>"
            f"<td>{html.escape(s['label'])}</td>"
            f"<td>{html.escape(s['region'])}</td>"
            f"<td class='num'>{s['interactions']}</td>"
            f"<td class='num'>{s['avg_turns']:.1f}</td>"
            f"<td class='num'>{s['completed']}/{s['interactions']} "
            f"({s['completion_rate']:.0f}%)</td>"
            f"<td class='num'>{s['avg_latency_s']:.1f}s</td>"
            f"</tr>"
        )

    # ── Flow table ─────────────────────────────────────────────────────────
    flow_rows = []
    for s in flow_stats:
        flow_rows.append(
            f"<tr>"
            f"<td>{html.escape(s['label'])}</td>"
            f"<td class='num'>{s['occurrences']}</td>"
            f"<td class='num'>{s['expected_weight_pct']:.0f}%</td>"
            f"<td class='num'>{s['actual_pct']:.0f}%</td>"
            f"<td class='num'>{s['avg_turns']:.1f}</td>"
            f"<td class='num'>{s['completed']}/{s['occurrences']} "
            f"({s['completion_rate']:.0f}%)</td>"
            f"</tr>"
        )

    # ── Conversations ──────────────────────────────────────────────────────
    conversations = "\n".join(
        _render_conversation(i, r) for i, r in enumerate(results)
    )

    completion_class = _completion_badge(summary["completion_rate"])

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Flowtest Report — {today}</title>
<script src="{CHART_JS_CDN}"></script>
<style>
  body {{ font-family: -apple-system, system-ui, "Segoe UI", sans-serif; max-width: 1200px; margin: 24px auto; padding: 0 16px; color: #1a202c; }}
  h1 {{ margin-bottom: 4px; color: #1a365d; }}
  h2 {{ margin-top: 32px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; color: #2d3748; }}
  .meta {{ color: #718096; margin-bottom: 24px; }}
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
  .card {{ background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }}
  .card .label {{ font-size: 12px; color: #718096; text-transform: uppercase; letter-spacing: 0.05em; }}
  .card .value {{ font-size: 28px; font-weight: 700; margin-top: 8px; color: #2d3748; }}
  .card .value-good {{ color: #22863a; }}
  .card .value-warn {{ color: #b7791f; }}
  .card .value-bad {{ color: #d73a49; }}
  .chart-wrap {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 24px; }}
  th, td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; text-align: left; }}
  th {{ background: #edf2f7; font-weight: 600; color: #2d3748; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  details {{ background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; margin-bottom: 8px; }}
  details summary {{ cursor: pointer; font-weight: 500; user-select: none; }}
  details[open] summary {{ margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }}
  table.turns-table {{ font-size: 13px; margin: 0; }}
  table.turns-table th {{ background: #f1f5f9; }}
  table.turns-table td.num {{ width: 32px; }}
  table.turns-table td.client {{ width: 28%; color: #2b6cb0; }}
  table.turns-table td.bot {{ width: 50%; }}
  table.turns-table td.intent {{ width: 12%; font-family: monospace; font-size: 12px; color: #4a5568; }}
  table.turns-table td.lat {{ width: 8%; text-align: right; font-variant-numeric: tabular-nums; }}
  tr.row-no-intent {{ background: #fee2e2; }}
  tr.row-slow {{ background: #fef9c3; }}
  tr:nth-child(even):not(.row-no-intent):not(.row-slow) {{ background: #f9fafb; }}
</style>
</head>
<body>
<h1>Flowtest Report — {today}</h1>
<div class="meta">{summary['total']} interações | {persona_count} personas | seed {seed_str}</div>

<div class="cards">
  <div class="card">
    <div class="label">Total interações</div>
    <div class="value">{summary['total']}</div>
  </div>
  <div class="card">
    <div class="label">Taxa de completude</div>
    <div class="value {completion_class}">{summary['completion_rate']:.0f}%</div>
  </div>
  <div class="card">
    <div class="label">Turnos médios</div>
    <div class="value">{summary['avg_turns']:.1f}</div>
  </div>
  <div class="card">
    <div class="label">Latência média/turno</div>
    <div class="value">{summary['avg_latency_per_turn_s']:.1f}s</div>
  </div>
</div>

<h2>Distribuição de fluxos — Esperado vs Realizado</h2>
<div class="chart-wrap"><canvas id="flowDistChart" height="80"></canvas></div>

<h2>Turnos médios por fluxo</h2>
<div class="chart-wrap"><canvas id="flowTurnsChart" height="80"></canvas></div>

<h2>Estatísticas por persona</h2>
<table>
  <thead>
    <tr>
      <th>Persona</th><th>Região</th><th>Interações</th>
      <th>Turnos médios</th><th>Completude</th><th>Latência média/turno</th>
    </tr>
  </thead>
  <tbody>{''.join(persona_rows)}</tbody>
</table>

<h2>Estatísticas por fluxo</h2>
<table>
  <thead>
    <tr>
      <th>Fluxo</th><th>Ocorrências</th><th>Peso esperado</th>
      <th>% Real</th><th>Turnos médios</th><th>Completude</th>
    </tr>
  </thead>
  <tbody>{''.join(flow_rows)}</tbody>
</table>

<h2>Conversas</h2>
{conversations}

<script>
  const flowDist = {flow_dist_data};
  new Chart(document.getElementById('flowDistChart'), {{
    type: 'bar',
    data: {{
      labels: flowDist.labels,
      datasets: [
        {{ label: 'Peso esperado (%)', data: flowDist.expected, backgroundColor: '#90cdf4' }},
        {{ label: 'Realizado (%)', data: flowDist.actual, backgroundColor: '#3182ce' }},
      ]
    }},
    options: {{
      indexAxis: 'y',
      scales: {{ x: {{ beginAtZero: true, title: {{ display: true, text: '%' }} }} }},
    }}
  }});

  const flowTurns = {flow_turns_data};
  new Chart(document.getElementById('flowTurnsChart'), {{
    type: 'bar',
    data: {{
      labels: flowTurns.labels,
      datasets: [{{
        label: 'Turnos médios',
        data: flowTurns.values,
        backgroundColor: '#4299e1',
      }}]
    }},
    options: {{
      indexAxis: 'y',
      scales: {{ x: {{ beginAtZero: true, title: {{ display: true, text: 'turnos' }} }} }},
      plugins: {{ legend: {{ display: false }} }}
    }}
  }});
</script>
</body>
</html>
"""


def generate_report(
    results: list[FlowTestResult],
    flows: list[dict[str, Any]],
    output_dir: Path | None = None,
    seed: int | None = None,
) -> tuple[Path, Path]:
    """Generate HTML and JSON reports.

    Returns ``(html_path, json_path)``.
    """
    out_dir = output_dir or Path("docs/evaluation/reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    html_path = out_dir / f"{today}_flowtest.html"
    json_path = out_dir / f"{today}_flowtest.json"

    raw = [r.to_dict() for r in results]
    json_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    html_content = _render_html(results, flows, today, seed)
    html_path.write_text(html_content, encoding="utf-8")

    return html_path, json_path
