"""telegram_autotest.py — testes automáticos do chatbot via Telegram Bot API.

Envia mensagens ao bot Camisart via Telegram, captura as respostas e gera
um relatório HTML com latências, status e respostas completas.

Pré-requisitos:
  1. Bot rodando em outro terminal: `python scripts/telegram_polling.py`
  2. .env com:
       TELEGRAM_BOT_TOKEN=<token do botfather>
       TELEGRAM_CHAT_ID=<chat_id do testador>

Como obter TELEGRAM_CHAT_ID (uma vez):
  1. Envie qualquer mensagem ao bot pelo Telegram
  2. Rode:
       python -c "import httpx, os; from dotenv import load_dotenv; load_dotenv();
       r=httpx.get(f'https://api.telegram.org/bot{os.getenv(\"TELEGRAM_BOT_TOKEN\")}/getUpdates');
       u=r.json()['result'];
       print('Chat ID:', u[-1]['message']['chat']['id']) if u else print('sem updates')"
  3. Copie o ID para .env: TELEGRAM_CHAT_ID=<id>

Uso:
  python scripts/telegram_autotest.py                 # roda suite default (faq)
  python scripts/telegram_autotest.py --suite all     # todas as suites
  python scripts/telegram_autotest.py --suite faq
  python scripts/telegram_autotest.py --suite llm
  python scripts/telegram_autotest.py --suite context
  python scripts/telegram_autotest.py --suite orcamento
  python scripts/telegram_autotest.py --suite edge
  python scripts/telegram_autotest.py --suite all --export

Saída --export:
  docs/evaluation/reports/YYYY-MM-DD_autotest.html

NOTA SOBRE CAPTURA DE RESPOSTA:
A captura usa `getUpdates` no bot e filtra por mensagens no chat do testador
desde o instante em que o teste começou. O Bot API entrega no `getUpdates`
as mensagens enviadas AO bot — para uso prático, o testador deve enviar via
Telegram regular, OU este script pode ser adaptado para usar um cliente
MTProto (Telethon) se for necessário simular um usuário. Por padrão o
script polleia getUpdates após cada envio e marca a primeira mensagem nova
no chat como resposta.
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

load_dotenv()

API_BASE = "https://api.telegram.org"
WAIT_RESPONSE_SECS = 15
INTER_MSG_DELAY = 2
POST_START_DELAY = 3


# ── Test cases ────────────────────────────────────────────────────────────────


@dataclass
class TestCase:
    suite: str
    message: str
    expected_keywords: list[str] = field(default_factory=list)
    is_reset: bool = False
    note: str = ""


@dataclass
class TestResult:
    suite: str
    message: str
    response: str
    expected_keywords: list[str]
    found_keywords: list[str]
    missing_keywords: list[str]
    latency_ms: float
    passed: bool
    layer_hint: str


SUITES: dict[str, list[TestCase]] = {
    "onboarding": [
        TestCase("onboarding", "/start", is_reset=True,
                 expected_keywords=["nome", "Camisart"]),
        TestCase("onboarding", "Thiago Autotest",
                 expected_keywords=["menu", "ajud"]),
    ],
    "faq": [
        TestCase("faq", "qual o preço da polo?",
                 ["polo", "piquet", "45"]),
        TestCase("faq", "quanto custa o jaleco?",
                 ["jaleco", "120"]),
        TestCase("faq", "onde fica a loja?",
                 ["Magalhães Barata"]),
        TestCase("faq", "tem pedido mínimo?",
                 ["mínimo", "1 peça"]),
        TestCase("faq", "aceita pix?",
                 ["PIX", "pagamento"]),
        TestCase("faq", "entrega em SP?",
                 ["Brasil", "Correios"]),
        TestCase("faq", "qual o prazo do bordado?",
                 ["bordado", "dias"]),
        TestCase("faq", "quero falar com atendente",
                 ["consultor", "atendimento"]),
    ],
    "llm": [
        TestCase("llm", "quanto fica aquela camisa com gola?",
                 ["polo", "piquet"]),
        TestCase("llm", "quero uniforme pra minha empresa",
                 ["uniforme", "orçamento"]),
    ],
    "context": [
        TestCase("context", "/start", is_reset=True,
                 expected_keywords=["nome", "Camisart"]),
        TestCase("context", "Thiago Autotest",
                 expected_keywords=["menu", "ajud"]),
        TestCase("context", "qual tecido é melhor pro calor de Belém?",
                 ["algodão", "PV"]),
        TestCase("context", "sublimação funciona em algodão?",
                 ["não", "poliéster"]),
        TestCase("context", "qual a diferença do jaleco premium?",
                 ["gabardine", "twill"]),
        TestCase("context", "quanto custa a programação do bordado?",
                 ["60", "80", "arte"]),
        TestCase("context", "qual jaleco pra uso hospitalar?",
                 ["gabardine", "consultor"]),
    ],
    "orcamento": [
        TestCase("orcamento", "/start", is_reset=True,
                 expected_keywords=["nome", "Camisart"]),
        TestCase("orcamento", "Thiago Autotest",
                 expected_keywords=["menu", "ajud"]),
        TestCase("orcamento", "quero fazer um orçamento",
                 expected_keywords=["segmento", "ramo"]),
        TestCase("orcamento", "Saúde",
                 expected_keywords=["produto", "jaleco"]),
        TestCase("orcamento", "Jaleco Tradicional",
                 expected_keywords=["quantidade", "peças"]),
        TestCase("orcamento", "5",
                 expected_keywords=["personaliza"]),
        TestCase("orcamento", "Bordado",
                 expected_keywords=["prazo"]),
        TestCase("orcamento", "15 dias",
                 expected_keywords=["confir"]),
        TestCase("orcamento", "sim",
                 expected_keywords=["orçamento", "consultor"]),
    ],
    "edge": [
        TestCase("edge", "qual o preço do bitcoin?",
                 [], note="deve cair em fallback (sem 'bitcoin price')"),
        TestCase("edge", "/start", is_reset=True,
                 expected_keywords=["nome", "Camisart"]),
        TestCase("edge", "aaaaaaaaa",
                 [], note="não pode crashar — qualquer resposta ok"),
    ],
}


# ── Telegram API helpers ──────────────────────────────────────────────────────


async def send_message(
    client: httpx.AsyncClient, token: str, chat_id: int, text: str
) -> dict:
    url = f"{API_BASE}/bot{token}/sendMessage"
    r = await client.post(
        url, json={"chat_id": chat_id, "text": text}, timeout=20.0
    )
    r.raise_for_status()
    return r.json()


async def fetch_updates(
    client: httpx.AsyncClient, token: str, offset: int, timeout: int = 5
) -> tuple[list[dict], int]:
    url = f"{API_BASE}/bot{token}/getUpdates"
    r = await client.get(
        url,
        params={"offset": offset, "timeout": timeout},
        timeout=timeout + 10,
    )
    r.raise_for_status()
    updates = r.json().get("result", [])
    new_offset = offset
    if updates:
        new_offset = updates[-1]["update_id"] + 1
    return updates, new_offset


async def wait_for_response(
    client: httpx.AsyncClient,
    token: str,
    chat_id: int,
    sent_at_unix: int,
    offset: int,
    timeout_secs: int = WAIT_RESPONSE_SECS,
) -> tuple[str, int]:
    """Poleia getUpdates por até `timeout_secs` esperando uma mensagem
    no chat alvo posterior a `sent_at_unix`. Retorna (texto, novo_offset)."""
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        remaining = max(1, int(deadline - time.time()))
        try:
            updates, offset = await fetch_updates(
                client, token, offset, timeout=min(5, remaining)
            )
        except httpx.HTTPError:
            await asyncio.sleep(0.5)
            continue
        for upd in updates:
            msg = upd.get("message") or upd.get("edited_message") or {}
            chat = msg.get("chat") or {}
            if chat.get("id") != chat_id:
                continue
            if msg.get("date", 0) < sent_at_unix:
                continue
            text = msg.get("text") or msg.get("caption") or ""
            if text:
                return text, offset
    return "", offset


async def drain_pending_updates(
    client: httpx.AsyncClient, token: str
) -> int:
    """Limpa updates antigos antes de iniciar — retorna offset inicial."""
    _, offset = await fetch_updates(client, token, offset=0, timeout=1)
    return offset


# ── Test execution ────────────────────────────────────────────────────────────


def evaluate(
    response: str, expected_keywords: list[str]
) -> tuple[list[str], list[str], bool]:
    found, missing = [], []
    resp_lower = response.lower()
    for kw in expected_keywords:
        (found if kw.lower() in resp_lower else missing).append(kw)
    passed = not missing if expected_keywords else bool(response)
    return found, missing, passed


def layer_for_latency(latency_ms: float) -> str:
    if latency_ms < 500:
        return "faq"
    if latency_ms < 3000:
        return "llm"
    return "context"


async def run_case(
    client: httpx.AsyncClient,
    token: str,
    chat_id: int,
    case: TestCase,
    offset: int,
) -> tuple[TestResult, int]:
    sent_at = int(time.time())
    t0 = time.perf_counter()
    await send_message(client, token, chat_id, case.message)
    response, offset = await wait_for_response(
        client, token, chat_id, sent_at, offset
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    found, missing, passed = evaluate(response, case.expected_keywords)
    result = TestResult(
        suite=case.suite,
        message=case.message,
        response=response,
        expected_keywords=case.expected_keywords,
        found_keywords=found,
        missing_keywords=missing,
        latency_ms=latency_ms,
        passed=passed,
        layer_hint=layer_for_latency(latency_ms),
    )
    return result, offset


async def run_suite(
    client: httpx.AsyncClient,
    token: str,
    chat_id: int,
    suite_name: str,
    offset: int,
) -> tuple[list[TestResult], int]:
    cases = SUITES[suite_name]
    results: list[TestResult] = []
    for case in cases:
        result, offset = await run_case(client, token, chat_id, case, offset)
        status = "OK" if result.passed else "FAIL"
        print(
            f"[{suite_name}] {status} ({result.latency_ms:6.0f}ms) "
            f"{case.message[:40]!r} -> {result.response[:60]!r}"
        )
        delay = POST_START_DELAY if case.is_reset else INTER_MSG_DELAY
        await asyncio.sleep(delay)
    return results, offset


async def run_all(
    token: str, chat_id: int, suite_names: list[str]
) -> list[TestResult]:
    all_results: list[TestResult] = []
    async with httpx.AsyncClient() as client:
        offset = await drain_pending_updates(client, token)
        for suite_name in suite_names:
            print(f"\n=== Suite: {suite_name} ===")
            results, offset = await run_suite(
                client, token, chat_id, suite_name, offset
            )
            all_results.extend(results)
    return all_results


# ── HTML report ───────────────────────────────────────────────────────────────


def render_html(results: list[TestResult], generated_at: datetime) -> str:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    avg_latency = (
        sum(r.latency_ms for r in results) / total if total else 0.0
    )

    by_layer: dict[str, list[float]] = {"faq": [], "llm": [], "context": []}
    for r in results:
        by_layer.setdefault(r.layer_hint, []).append(r.latency_ms)
    layer_avg = {
        k: (sum(v) / len(v) if v else 0.0) for k, v in by_layer.items()
    }

    rows = []
    for r in results:
        if r.latency_ms < 500:
            badge = "ok"
        elif r.latency_ms < 3000:
            badge = "warn"
        else:
            badge = "slow"
        status = "✅" if r.passed else "❌"
        kw_html = (
            f"<span class='kw-ok'>✓ {', '.join(html.escape(k) for k in r.found_keywords) or '—'}</span><br>"
            f"<span class='kw-miss'>✗ {', '.join(html.escape(k) for k in r.missing_keywords) or '—'}</span>"
        )
        rows.append(
            f"<tr>"
            f"<td>{html.escape(r.suite)}</td>"
            f"<td><code>{html.escape(r.message)}</code></td>"
            f"<td>{html.escape(r.response[:200])}{'…' if len(r.response) > 200 else ''}</td>"
            f"<td><span class='badge {badge}'>{r.latency_ms:.0f}ms</span></td>"
            f"<td>{status}</td>"
            f"<td>{kw_html}</td>"
            f"</tr>"
        )

    details_blocks = []
    for i, r in enumerate(results):
        details_blocks.append(
            f"<details><summary>"
            f"[{html.escape(r.suite)}] "
            f"{html.escape(r.message)} ({r.latency_ms:.0f}ms)"
            f"</summary>"
            f"<pre>{html.escape(r.response)}</pre>"
            f"</details>"
        )

    chart_data = json.dumps(
        {
            "labels": list(layer_avg.keys()),
            "values": [round(v, 1) for v in layer_avg.values()],
        }
    )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Camisart AI — Teste Automático {generated_at:%Y-%m-%d %H:%M}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: -apple-system, system-ui, "Segoe UI", sans-serif; max-width: 1200px; margin: 24px auto; padding: 0 16px; color: #1a202c; }}
  h1 {{ margin-bottom: 4px; }}
  .meta {{ color: #718096; margin-bottom: 24px; }}
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
  .card {{ background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }}
  .card .label {{ font-size: 12px; color: #718096; text-transform: uppercase; letter-spacing: 0.05em; }}
  .card .value {{ font-size: 28px; font-weight: 700; margin-top: 8px; }}
  .card.pass .value {{ color: #22863a; }}
  .card.fail .value {{ color: #d73a49; }}
  .chart-wrap {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 32px; max-width: 600px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; text-align: left; }}
  th {{ background: #f7fafc; font-weight: 600; }}
  code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
  .badge.ok {{ background: #c6f6d5; color: #22543d; }}
  .badge.warn {{ background: #fefcbf; color: #744210; }}
  .badge.slow {{ background: #fed7d7; color: #742a2a; }}
  .kw-ok {{ color: #22863a; font-size: 12px; }}
  .kw-miss {{ color: #d73a49; font-size: 12px; }}
  details {{ background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; margin-bottom: 8px; }}
  details summary {{ cursor: pointer; font-weight: 500; }}
  details pre {{ white-space: pre-wrap; background: #fff; padding: 12px; border-radius: 4px; margin-top: 8px; font-size: 13px; }}
  h2 {{ margin-top: 32px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
</style>
</head>
<body>
<h1>Camisart AI — Teste Automático</h1>
<div class="meta">Gerado em {generated_at:%Y-%m-%d %H:%M:%S}</div>

<div class="cards">
  <div class="card"><div class="label">Total</div><div class="value">{total}</div></div>
  <div class="card pass"><div class="label">✅ Passed</div><div class="value">{passed}</div></div>
  <div class="card fail"><div class="label">❌ Failed</div><div class="value">{failed}</div></div>
  <div class="card"><div class="label">Avg Latency</div><div class="value">{avg_latency:.0f}ms</div></div>
</div>

<h2>Latência média por camada</h2>
<div class="chart-wrap"><canvas id="latencyChart"></canvas></div>

<h2>Resultados por suite</h2>
<table>
  <thead>
    <tr>
      <th>Suite</th><th>Mensagem</th><th>Resposta (200 chars)</th>
      <th>Latência</th><th>Status</th><th>Keywords</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>

<h2>Respostas completas para revisão</h2>
{''.join(details_blocks)}

<script>
  const data = {chart_data};
  new Chart(document.getElementById('latencyChart'), {{
    type: 'bar',
    data: {{
      labels: data.labels,
      datasets: [{{
        label: 'Latência média (ms)',
        data: data.values,
        backgroundColor: ['#48bb78', '#ecc94b', '#f56565'],
      }}]
    }},
    options: {{
      scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'ms' }} }} }},
      plugins: {{ legend: {{ display: false }} }}
    }}
  }});
</script>
</body>
</html>
"""


def export_html(results: list[TestResult]) -> Path:
    out_dir = Path("docs/evaluation/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    out = out_dir / f"{now:%Y-%m-%d}_autotest.html"
    out.write_text(render_html(results, now), encoding="utf-8")
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    suites = list(SUITES.keys()) + ["all"]
    p = argparse.ArgumentParser(
        description="Testes automáticos do bot via Telegram Bot API.",
    )
    p.add_argument(
        "--suite", choices=suites, default="faq",
        help="Suite a executar (default: faq).",
    )
    p.add_argument(
        "--export", action="store_true",
        help="Gera relatório HTML em docs/evaluation/reports/.",
    )
    p.add_argument(
        "--chat-id", type=int, default=None,
        help="Override TELEGRAM_CHAT_ID do .env.",
    )
    return p.parse_args()


async def amain() -> int:
    args = parse_args()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id_str = os.getenv("TELEGRAM_CHAT_ID", "")
    chat_id = args.chat_id or (int(chat_id_str) if chat_id_str else 0)

    if not token:
        print("ERRO: TELEGRAM_BOT_TOKEN não configurado em .env", file=sys.stderr)
        return 2
    if not chat_id:
        print(
            "ERRO: TELEGRAM_CHAT_ID não configurado.\n"
            "Envie /start ao bot e rode:\n"
            "  python -c \"import httpx,os; from dotenv import load_dotenv;"
            " load_dotenv();"
            " r=httpx.get(f'https://api.telegram.org/bot{os.getenv(\\\"TELEGRAM_BOT_TOKEN\\\")}/getUpdates');"
            " u=r.json()['result'];"
            " print(u[-1]['message']['chat']['id']) if u else print('sem updates')\"\n"
            "Copie o ID para .env: TELEGRAM_CHAT_ID=<id>",
            file=sys.stderr,
        )
        return 2

    suite_names = list(SUITES.keys()) if args.suite == "all" else [args.suite]
    results = await run_all(token, chat_id, suite_names)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    avg_latency = (
        sum(r.latency_ms for r in results) / total if total else 0.0
    )

    print()
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Resumo: {passed}/{total} passed · {failed} failed "
          f"· avg {avg_latency:.0f}ms")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if args.export:
        path = export_html(results)
        print(f"Relatório HTML: {path}")

    return 0 if failed == 0 else 1


def main() -> None:
    sys.exit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
