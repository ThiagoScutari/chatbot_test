"""
Gera dashboard HTML com graficos interativos a partir do relatorio
de avaliacao do Camisart AI.

Uso:
    # Primeiro gerar o relatorio:
    python scripts/evaluate.py --export

    # Depois gerar o dashboard:
    python scripts/dashboard.py

    # Ou especificar o relatorio:
    python scripts/dashboard.py --report docs/evaluation/reports/2026-04-23_report.json

O HTML gerado pode ser aberto em qualquer browser sem servidor.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPORTS_DIR = Path("docs/evaluation/reports")
CHART_JS_CDN = (
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"
)


def grade_color(value: float) -> str:
    if value >= 0.95:
        return "#22c55e"
    if value >= 0.85:
        return "#3b82f6"
    if value >= 0.75:
        return "#f59e0b"
    return "#ef4444"


def grade_label(value: float) -> str:
    if value >= 0.95:
        return "Excelente"
    if value >= 0.85:
        return "Bom"
    if value >= 0.75:
        return "Regular"
    return "Precisa melhorar"


LAYER_LABELS = {
    "faq":     "FAQ Automático",
    "llm":     "Entendimento Avançado",
    "rag":     "Consulta Técnica",
    "context": "Consulta Técnica",
    "none":    "Fora do Escopo",
}

INTENT_LABELS = {
    "preco_polo":           "Preço da Polo",
    "preco_jaleco":         "Preço do Jaleco",
    "bordado_prazo":        "Prazo/Info do Bordado",
    "pedido_minimo":        "Pedido Mínimo",
    "prazo_entrega":        "Prazo de Entrega",
    "entrega_nacional":     "Entrega Nacional",
    "falar_humano":         "Falar com Atendente",
    "pagamento":            "Formas de Pagamento",
    "feminino":             "Linha Feminina",
    "desconto_quantidade":  "Desconto por Quantidade",
    "tamanhos_disponiveis": "Tamanhos Disponíveis",
    "endereco":             "Endereço",
    "contato_whatsapp":     "Contato WhatsApp",
    "manga_longa":          "Manga Longa",
    "dry_fit":              "Uniformes Esportivos",
    "instagram_referencia": "Referência do Instagram",
    "segmento_negocio":     "Segmento do Negócio",
    "estoque_pronto":       "Estoque / Pronta Entrega",
    "pos_venda":            "Pós-venda",
    "orcamento_trigger":    "Solicitar Orçamento",
    "rag_response":         "Pergunta Técnica",
    "none":                 "Fora do Escopo",
    "context_response":     "Resposta Técnica",
}


def generate_dashboard(report: dict, output_path: Path) -> None:
    intents = list(report["f1_per_intent"].keys())
    f1_values = [report["f1_per_intent"][i] * 100 for i in intents]
    precision_values = [
        report["precision_per_intent"].get(i, 0) * 100 for i in intents
    ]
    recall_values = [
        report["recall_per_intent"].get(i, 0) * 100 for i in intents
    ]

    sorted_pairs = sorted(
        zip(intents, f1_values, precision_values, recall_values),
        key=lambda x: x[1],
        reverse=True,
    )
    intents_s = [p[0] for p in sorted_pairs]
    intents_s_display = [INTENT_LABELS.get(i, i) for i in intents_s]
    f1_s = [p[1] for p in sorted_pairs]
    precision_s = [p[2] for p in sorted_pairs]
    recall_s = [p[3] for p in sorted_pairs]

    cm = report["confusion_matrix"]
    cm_labels = report["confusion_labels"]

    # Acertos por intent (substitui matriz de confusão) [fix-M4]
    support_per_intent = report.get("support_per_intent", {})
    intent_accuracy = {}
    for intent in intents:
        if intent not in cm_labels:
            continue
        idx = cm_labels.index(intent)
        tp = cm[idx][idx]
        total = support_per_intent.get(intent, 0)
        if total > 0:
            intent_accuracy[intent] = {
                "label": INTENT_LABELS.get(intent, intent),
                "correct": int(tp),
                "total": int(total),
                "pct": round(tp / total * 100, 1),
            }

    layers = report.get("accuracy_by_layer", {})
    layer_names = list(layers.keys())
    layer_names_display = [LAYER_LABELS.get(n, n) for n in layer_names]
    layer_accs = [v * 100 for v in layers.values()]

    diffs = report.get("accuracy_by_difficulty", {})

    accuracy = report["accuracy"] * 100
    f1_macro = report["f1_macro"] * 100
    fallback = report["fallback_rate"] * 100
    total = report["total_samples"]

    lats = report.get("avg_latency_by_layer", {})
    lat_faq = lats.get("faq", 0)
    diff_labels_display = {
        {"easy": "Fácil", "medium": "Médio", "hard": "Difícil"}.get(k, k): v
        for k, v in diffs.items()
    }
    lat_labels_display = {LAYER_LABELS.get(k, k): v for k, v in lats.items()}

    top_errors = report.get("top_errors", [])[:5]
    errors_html = ""
    for err in top_errors:
        examples = "<br>".join(
            f'<em>"{ex[:60]}"</em>' for ex in err.get("examples", [])[:2]
        )
        expected_label = INTENT_LABELS.get(err["expected"], err["expected"])
        predicted_label = INTENT_LABELS.get(err["predicted"], err["predicted"])
        errors_html += f"""
        <tr>
          <td>
            <span style="background:#fee2e2;color:#991b1b;padding:2px 8px;
            border-radius:4px;font-size:12px">{expected_label}</span>
            &rarr; <span style="background:#e0e7ff;color:#3730a3;padding:2px 8px;
            border-radius:4px;font-size:12px">{predicted_label}</span>
          </td>
          <td style="text-align:center;font-weight:bold">{err["count"]}x</td>
          <td style="color:#6b7280">{examples}</td>
        </tr>"""

    good_intents = [INTENT_LABELS.get(i, i) for i, f in zip(intents_s, f1_s) if f >= 90]
    weak_intents = [INTENT_LABELS.get(i, i) for i, f in zip(intents_s, f1_s) if f < 80]
    exec_good = ", ".join(good_intents[:4]) if good_intents else "-"
    exec_weak = ", ".join(weak_intents[:3]) if weak_intents else "nenhum"

    date_str = report.get("timestamp", "")[:10]

    weak_tail = (
        " - adicionar variacoes linguisticas ao FAQ."
        if exec_weak != "nenhum"
        else ""
    )
    fallback_line = (
        "esta dentro da meta de 10%."
        if fallback < 10
        else "esta acima da meta de 10% - revisar intents com recall baixo."
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Camisart AI - Relatorio de Desempenho</title>
  <script src="{CHART_JS_CDN}"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f8fafc; color: #1e293b;
      padding: 16px;
      max-width: 1400px;
      margin: 0 auto;
    }}
    .header {{
      background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
      color: white; padding: 32px 40px; border-radius: 16px;
      margin-bottom: 24px;
    }}
    .header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 6px; }}
    .header p {{ opacity: 0.8; font-size: 15px; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 16px; margin-bottom: 24px;
    }}
    .card {{
      background: white; border-radius: 12px; padding: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center;
    }}
    .card .value {{ font-size: 36px; font-weight: 700; margin-bottom: 4px; }}
    .card .label {{ font-size: 13px; color: #64748b; text-transform: uppercase;
                    letter-spacing: 0.05em; }}
    .card .grade {{ font-size: 12px; margin-top: 4px; font-weight: 500; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr;
               gap: 20px; margin-bottom: 24px; }}
    .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr;
               gap: 20px; margin-bottom: 24px; }}
    .panel {{
      background: white; border-radius: 12px; padding: 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    .panel h2 {{
      font-size: 16px; font-weight: 600; margin-bottom: 16px;
      color: #334155; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;
    }}
    .exec-panel {{
      background: #f0f9ff; border: 1px solid #bae6fd;
      border-radius: 12px; padding: 24px; margin-bottom: 24px;
    }}
    .exec-panel h2 {{ color: #0369a1; margin-bottom: 12px; font-size: 18px; }}
    .exec-panel p {{ line-height: 1.7; color: #334155; margin-bottom: 8px; }}
    .tag-good {{
      background: #dcfce7; color: #166534; padding: 3px 10px;
      border-radius: 20px; font-size: 13px; font-weight: 500;
    }}
    .tag-warn {{
      background: #fef9c3; color: #854d0e; padding: 3px 10px;
      border-radius: 20px; font-size: 13px; font-weight: 500;
    }}
    .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 400px; }}
    th {{ text-align: left; padding: 8px; background: #f8fafc;
          font-size: 13px; color: #64748b; border-bottom: 2px solid #e2e8f0; }}
    td {{ padding: 8px; border-bottom: 1px solid #e5e7eb;
          font-size: 13px; vertical-align: top; }}
    .chart-container {{ position: relative; width: 100%; }}
    canvas {{ width: 100% !important; }}

    /* Tablet */
    @media (max-width: 1024px) {{
      .cards {{ grid-template-columns: repeat(3, 1fr); }}
    }}

    /* Mobile */
    @media (max-width: 768px) {{
      body {{ padding: 12px; }}
      .header {{ padding: 20px; border-radius: 12px; }}
      .header h1 {{ font-size: 20px; }}
      .header p {{ font-size: 13px; }}
      .cards {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
      .card {{ padding: 14px; }}
      .card .value {{ font-size: 26px; }}
      .card .label {{ font-size: 11px; }}
      .grid-2, .grid-3 {{ grid-template-columns: 1fr; gap: 12px; }}
      .panel {{ padding: 16px; }}
      .panel h2 {{ font-size: 14px; }}
      .exec-panel {{ padding: 16px; }}
      .exec-panel h2 {{ font-size: 16px; }}
      th, td {{ padding: 6px 8px; font-size: 12px; }}
    }}

    /* Small phone */
    @media (max-width: 480px) {{
      .cards {{ grid-template-columns: 1fr 1fr; }}
      .card .value {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>

<div class="header">
  <h1>Camisart AI - Relatorio de Desempenho</h1>
  <p>Avaliacao em {total} mensagens reais | {date_str} |
     FAQ Automático · Entendimento Avançado · Consulta Técnica</p>
</div>

<div class="cards">
  <div class="card">
    <div class="value" style="color:{grade_color(accuracy / 100)}">{accuracy:.1f}%</div>
    <div class="label">Accuracy Global</div>
    <div class="grade" style="color:{grade_color(accuracy / 100)}">
      {grade_label(accuracy / 100)}</div>
  </div>
  <div class="card">
    <div class="value" style="color:{grade_color(f1_macro / 100)}">{f1_macro:.1f}%</div>
    <div class="label">F1 Macro</div>
    <div class="grade" style="color:{grade_color(f1_macro / 100)}">
      {grade_label(f1_macro / 100)}</div>
  </div>
  <div class="card">
    <div class="value" style="color:{"#22c55e" if fallback < 10 else "#f59e0b"}">{fallback:.1f}%</div>
    <div class="label">Fallback Indevido</div>
    <div class="grade" style="color:{"#22c55e" if fallback < 10 else "#f59e0b"}">
      {"Dentro da meta" if fallback < 10 else "Acima da meta"}</div>
  </div>
  <div class="card">
    <div class="value" style="color:#3b82f6">{lat_faq:.0f}ms</div>
    <div class="label">Latencia FAQ</div>
    <div class="grade" style="color:#3b82f6">Camada 1</div>
  </div>
  <div class="card">
    <div class="value" style="color:#8b5cf6">{total}</div>
    <div class="label">Amostras Avaliadas</div>
    <div class="grade" style="color:#8b5cf6">ground truth</div>
  </div>
</div>

<div class="exec-panel">
  <h2>Analise Executiva</h2>
  <p>
    O chatbot da Camisart respondeu corretamente
    <strong>{accuracy:.1f}%</strong> das perguntas testadas ({total} mensagens).
    Com F1 macro de <strong>{f1_macro:.1f}%</strong>, o sistema demonstra
    equilibrio entre precisao e cobertura - nao deixa perguntas sem resposta
    e nao responde de forma incorreta com frequencia.
  </p>
  <p>
    <strong>Pontos fortes:</strong>
    <span class="tag-good">{exec_good}</span> - todos com F1 acima de 90%.
  </p>
  <p>
    <strong>Oportunidades de melhoria:</strong>
    <span class="tag-warn">{exec_weak if exec_weak != "nenhum" else "nenhum identificado"}</span>{weak_tail}
  </p>
  <p>
    A taxa de fallback indevido de <strong>{fallback:.1f}%</strong>
    {fallback_line}
  </p>
</div>

<div class="grid-2">
  <div class="panel">
    <h2>F1 Score por Intencao</h2>
    <div class="chart-container" style="height:350px;">
      <canvas id="f1Chart"></canvas>
    </div>
  </div>
  <div class="panel">
    <h2>Precision vs Recall por Intencao</h2>
    <div class="chart-container" style="height:350px;">
      <canvas id="prChart"></canvas>
    </div>
  </div>
</div>

<div class="grid-3">
  <div class="panel">
    <h2>Distribuicao por Camada</h2>
    <div class="chart-container" style="height:350px;">
      <canvas id="layerChart"></canvas>
    </div>
    <div style="margin-top:12px;font-size:12px;color:#64748b;line-height:2">
      <b>FAQ Automático</b> — respostas instantâneas para perguntas frequentes<br>
      <b>Entendimento Avançado</b> — interpreta linguagem livre e informal<br>
      <b>Consulta Técnica</b> — responde dúvidas técnicas sobre produtos<br>
      <b>Fora do Escopo</b> — perguntas não relacionadas à Camisart
    </div>
  </div>
  <div class="panel">
    <h2>Acuracia por Dificuldade</h2>
    <div class="chart-container" style="height:350px;">
      <canvas id="diffChart"></canvas>
    </div>
  </div>
  <div class="panel">
    <h2>Latencia por Camada</h2>
    <div class="chart-container" style="height:350px;">
      <canvas id="latChart"></canvas>
    </div>
  </div>
</div>

<div class="panel" style="margin-bottom:24px">
  <h2>✅ Acertos por Tipo de Pergunta</h2>
  <p style="font-size:13px;color:#64748b;margin-bottom:16px">
    Para cada tipo de pergunta, quantas vezes o bot respondeu corretamente.
  </p>
  <div class="chart-container" style="height:550px;">
    <canvas id="accuracyChart"></canvas>
  </div>
</div>

<div class="panel" style="margin-bottom:24px">
  <h2>Erros Mais Frequentes</h2>
  <div class="table-wrap">
  <table>
    <tr>
      <th>Confusão (real → predito)</th>
      <th>Qtd</th>
      <th>Exemplos de mensagens</th>
    </tr>
    {errors_html if errors_html else '<tr><td colspan="3" style="padding:16px;text-align:center;color:#6b7280">Nenhum erro registrado</td></tr>'}
  </table>
  </div>
</div>

<script>
const intents = {json.dumps(intents_s_display, ensure_ascii=False)};
const f1Values = {json.dumps([round(v, 1) for v in f1_s])};
const precValues = {json.dumps([round(v, 1) for v in precision_s])};
const recValues = {json.dumps([round(v, 1) for v in recall_s])};
const accuracyData = {json.dumps(intent_accuracy, ensure_ascii=False)};
const layerNames = {json.dumps(layer_names_display, ensure_ascii=False)};
const layerAccs = {json.dumps([round(v, 1) for v in layer_accs])};
const diffData = {json.dumps({k: round(v * 100, 1) for k, v in diff_labels_display.items()}, ensure_ascii=False)};
const latData = {json.dumps({k: round(v, 0) for k, v in lat_labels_display.items()}, ensure_ascii=False)};

const COLORS = [
  '#3b82f6','#22c55e','#f59e0b','#ef4444','#8b5cf6',
  '#06b6d4','#f97316','#84cc16','#ec4899','#6366f1',
  '#14b8a6','#a855f7','#fb923c','#64748b'
];

function colorForVal(v) {{
  if (v >= 95) return '#22c55e';
  if (v >= 85) return '#3b82f6';
  if (v >= 75) return '#f59e0b';
  return '#ef4444';
}}

new Chart(document.getElementById('f1Chart'), {{
  type: 'bar',
  data: {{
    labels: intents,
    datasets: [{{
      label: 'F1 Score (%)',
      data: f1Values,
      backgroundColor: f1Values.map(colorForVal),
      borderRadius: 6,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ min: 0, max: 100, ticks: {{ callback: v => v + '%' }} }},
      y: {{ ticks: {{ font: {{ size: 11 }} }} }}
    }}
  }}
}});

new Chart(document.getElementById('prChart'), {{
  type: 'scatter',
  data: {{
    datasets: intents.map((label, i) => ({{
      label,
      data: [{{ x: precValues[i], y: recValues[i] }}],
      backgroundColor: COLORS[i % COLORS.length],
      pointRadius: 8,
      pointHoverRadius: 10,
    }}))
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'right', labels: {{ font: {{ size: 11 }} }} }},
      tooltip: {{
        callbacks: {{
          label: ctx => `${{ctx.dataset.label}}: P=${{ctx.parsed.x}}% R=${{ctx.parsed.y}}%`
        }}
      }}
    }},
    scales: {{
      x: {{ min: 0, max: 100, title: {{ display: true, text: 'Precision (%)' }} }},
      y: {{ min: 0, max: 100, title: {{ display: true, text: 'Recall (%)' }} }}
    }}
  }}
}});

new Chart(document.getElementById('layerChart'), {{
  type: 'doughnut',
  data: {{
    labels: layerNames,
    datasets: [{{
      data: layerAccs,
      backgroundColor: ['#3b82f6','#8b5cf6','#22c55e','#64748b'],
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'bottom' }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.label + ': ' + ctx.parsed + '%' }} }}
    }}
  }}
}});

new Chart(document.getElementById('diffChart'), {{
  type: 'bar',
  data: {{
    labels: Object.keys(diffData),
    datasets: [{{
      label: 'Accuracy (%)',
      data: Object.values(diffData),
      backgroundColor: ['#22c55e','#3b82f6','#f59e0b'],
      borderRadius: 8,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ min: 0, max: 100 }} }}
  }}
}});

new Chart(document.getElementById('latChart'), {{
  type: 'bar',
  data: {{
    labels: Object.keys(latData),
    datasets: [{{
      label: 'Latencia (ms)',
      data: Object.values(latData),
      backgroundColor: ['#3b82f6','#8b5cf6','#22c55e','#64748b'],
      borderRadius: 8,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ title: {{ display: true, text: 'ms' }} }} }}
  }}
}});

const sortedAccuracy = Object.entries(accuracyData)
  .filter(([k, v]) => v.total > 0)
  .sort((a, b) => b[1].pct - a[1].pct);

new Chart(document.getElementById('accuracyChart'), {{
  type: 'bar',
  data: {{
    labels: sortedAccuracy.map(([k, v]) => v.label),
    datasets: [
      {{
        label: 'Acertos',
        data: sortedAccuracy.map(([k, v]) => v.correct),
        backgroundColor: '#22c55e',
        borderRadius: 4,
      }},
      {{
        label: 'Erros',
        data: sortedAccuracy.map(([k, v]) => v.total - v.correct),
        backgroundColor: '#ef4444',
        borderRadius: 4,
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: {{
      legend: {{ position: 'top' }},
      tooltip: {{
        callbacks: {{
          afterBody: (items) => {{
            const idx = items[0].dataIndex;
            const d = sortedAccuracy[idx][1];
            return ['Acurácia: ' + d.pct + '% (' + d.correct + '/' + d.total + ')'];
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ stacked: true, title: {{ display: true, text: 'Número de perguntas' }} }},
      y: {{ stacked: true, ticks: {{ font: {{ size: 11 }} }} }}
    }}
  }}
}});
</script>

</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"Dashboard salvo em: {output_path}")
    print(f"   Abrir no browser: file:///{output_path.resolve()}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        help="Caminho do JSON gerado por evaluate.py --export",
    )
    args = parser.parse_args()

    if args.report:
        report_path = Path(args.report)
    else:
        reports = sorted(REPORTS_DIR.glob("*_report.json"), reverse=True)
        if not reports:
            print("Nenhum relatorio encontrado.")
            print("Execute primeiro: python scripts/evaluate.py --export")
            return
        report_path = reports[0]
        print(f"Usando relatorio: {report_path.name}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    date_str = report_path.stem.replace("_report", "")
    output_path = REPORTS_DIR / f"{date_str}_dashboard.html"

    generate_dashboard(report, output_path)


if __name__ == "__main__":
    main()
