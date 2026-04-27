"""autotest.py — testes automáticos do chatbot via pipeline direto.

Não depende do Telegram. Aciona MessagePipeline.process() diretamente
e captura as respostas reais do bot. Mede latência por mensagem e
gera relatório HTML.

As Camadas 2 (LLMRouter) e 3 (ContextEngine) chamam APIs reais
(Claude Haiku) se ANTHROPIC_API_KEY estiver configurada. Use
`--mock-llm` para rodar offline com apenas Camada 1 (FAQ regex).

Uso:
  python scripts/autotest.py                   # roda todas as suites
  python scripts/autotest.py --suite faq       # só Camada 1
  python scripts/autotest.py --suite context   # só Camada 3
  python scripts/autotest.py --mock-llm        # offline
  python scripts/autotest.py --export          # gera HTML em docs/evaluation/reports/

Banco usado: TEST_DATABASE_URL (fallback DATABASE_URL).
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Garante saída UTF-8 no terminal Windows (cp1252 não imprime emojis).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

load_dotenv()

# Imports após sys.path
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.engines.campaign_engine import CampaignEngine  # noqa: E402
from app.engines.regex_engine import FAQEngine  # noqa: E402
from app.pipeline.message_pipeline import MessagePipeline  # noqa: E402

# Registra modelos no Base.metadata
import app.models.session  # noqa: E402, F401
import app.models.message  # noqa: E402, F401
import app.models.lead  # noqa: E402, F401
import app.models.audit_log  # noqa: E402, F401
import app.models.knowledge_chunk  # noqa: E402, F401


# ── Test cases ────────────────────────────────────────────────────────────────


@dataclass
class TestCase:
    suite: str
    message: str
    expected_keywords: list[str] = field(default_factory=list)
    is_reset: bool = False
    note: str = ""


@dataclass
class AutoTestResult:
    suite: str
    message: str
    response: str = ""
    expected_keywords: list[str] = field(default_factory=list)
    found_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    passed: bool = False
    layer_hint: str = "unknown"
    error: str = ""


# Suites de teste — ~100+ casos cobrindo:
# (1) abreviações (vc, qto, pfv); (2) sotaque/regionalismos paraenses (égua,
# mano, oxe); (3) gírias informais (tô afim, me passa); (4) frases incompletas;
# (5) erros ortográficos; (6) perguntas multi-intenção; (7) edge cases.
# Cada suite com is_reset=True na primeira mensagem cria channel_user_id único
# (uuid) — sem contaminação entre runs ou entre suites [autotest-v2].
SUITES: dict[str, list[TestCase]] = {
    "onboarding": [
        TestCase("onboarding", "/start", is_reset=True,
                 expected_keywords=["Camisart", "prazer"]),
        TestCase("onboarding", "Thiago Autotest",
                 expected_keywords=["Prazer", "ajud"]),
        TestCase("onboarding", "/start", is_reset=True,
                 expected_keywords=["Camisart", "prazer"]),
        TestCase("onboarding", "João da Silva",
                 expected_keywords=["Prazer", "ajud"]),
    ],
    "faq": [
        # Bloco 1 — preco_polo + preco_jaleco
        TestCase("faq", "/start", is_reset=True),
        TestCase("faq", "Cliente FAQ A"),
        TestCase("faq", "qual o preço da polo?",
                 ["polo", "piquet", "45"]),
        TestCase("faq", "qto custa a polo piquet?",
                 ["polo", "piquet", "45"]),
        TestCase("faq", "me passa o valor da camisa polo",
                 ["polo", "45"]),
        TestCase("faq", "quanto custa o jaleco?",
                 ["jaleco", "120"]),
        TestCase("faq", "jaleco medico quanto?",
                 ["jaleco", "120"]),
        TestCase("faq", "égua qto ta o jaleco lá?",
                 ["jaleco", "120"]),
        # Bloco 2 — endereco + pedido_minimo
        TestCase("faq", "/start", is_reset=True),
        TestCase("faq", "Cliente FAQ B"),
        TestCase("faq", "onde fica a loja?",
                 ["Magalhães"]),
        TestCase("faq", "pfv me passa o endereço",
                 ["Magalhães"]),
        TestCase("faq", "qual o end de vcs?",
                 ["Magalhães"]),
        TestCase("faq", "tem pedido mínimo?",
                 ["mínimo", "1"]),
        TestCase("faq", "posso comprar 1 peça só?",
                 ["mínimo", "1"]),
        TestCase("faq", "compro avulso?",
                 ["mínimo", "1"]),
        # Bloco 3 — pagamento + entrega_nacional
        TestCase("faq", "/start", is_reset=True),
        TestCase("faq", "Cliente FAQ C"),
        TestCase("faq", "aceita pix?",
                 ["PIX", "pagamento"]),
        TestCase("faq", "paga no debito?",
                 ["débito", "pagamento"]),
        TestCase("faq", "tem parcelamento?",
                 ["crédito", "parcelamento"]),
        TestCase("faq", "entrega em SP?",
                 ["Brasil", "Correios"]),
        TestCase("faq", "vc manda pros Correios?",
                 ["Brasil", "Correios"]),
        TestCase("faq", "entega fora de Belém tb?",
                 ["Brasil", "Correios"]),
        # Bloco 4 — bordado_prazo + falar_humano
        TestCase("faq", "/start", is_reset=True),
        TestCase("faq", "Cliente FAQ D"),
        TestCase("faq", "qual o prazo do bordado?",
                 ["bordado", "dias"]),
        TestCase("faq", "burdado demora qtos dias?",
                 ["bordado", "dias"]),
        TestCase("faq", "em qto tempo fica o bordado?",
                 ["bordado", "dias"]),
        TestCase("faq", "quero falar com atendente",
                 ["consultor", "atendimento"]),
        TestCase("faq", "me passa pra um humano",
                 ["consultor"]),
        TestCase("faq", "quero falar c/ alguem",
                 ["consultor"]),
        # Bloco 5 — prazo_entrega + desconto_quantidade
        TestCase("faq", "/start", is_reset=True),
        TestCase("faq", "Cliente FAQ E"),
        TestCase("faq", "qual o prazo da entrega?",
                 ["prazo", "dias"]),
        TestCase("faq", "qto tempo demora pra chegar?",
                 ["prazo", "dias"]),
        TestCase("faq", "preciso rápido, e o prazo?",
                 ["prazo", "dias"]),
        TestCase("faq", "tem desconto na quantidade?",
                 ["desconto", "atacado"]),
        TestCase("faq", "se comprar 50 peças fica mais barato?",
                 ["atacado", "especial"]),
        TestCase("faq", "preço de atacado como funciona?",
                 ["atacado", "12"]),
    ],
    "llm": [
        # Bloco 1
        TestCase("llm", "/start", is_reset=True),
        TestCase("llm", "Cliente LLM A"),
        TestCase("llm", "quanto fica aquela camisa com gola?",
                 ["polo", "piquet"]),
        TestCase("llm", "quero uniforme pra minha empresa",
                 ["uniforme", "orçamento"]),
        TestCase("llm", "tô querendo uma camisa com gola pro meu pessoal",
                 ["polo", "piquet"]),
        TestCase("llm", "mano, que camisa fica bem pra equipe de vendas?",
                 ["polo", "uniforme"]),
        TestCase("llm", "égua, faz uniforme pra padaria não?",
                 ["uniforme", "segmento"]),
        # Bloco 2
        TestCase("llm", "/start", is_reset=True),
        TestCase("llm", "Cliente LLM B"),
        TestCase("llm", "bora fazer uns uniforme corporativo",
                 ["uniforme", "orçamento"]),
        TestCase("llm", "qual roupa boa pra dentista?",
                 ["jaleco"]),
        TestCase("llm", "tô afim de personalizar umas peças pro meu time",
                 ["personaliz", "bordado"]),
        TestCase("llm", "quero algo profissional pra minha recepção",
                 ["polo", "uniforme"]),
        TestCase("llm", "tem roupa pra academia?",
                 ["esport", "dry"]),
    ],
    "context": [
        # Bloco 1 — originais + tecidos/clima
        TestCase("context", "/start", is_reset=True),
        TestCase("context", "Cliente CTX A"),
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
        # Bloco 2 — tecidos/clima + sublimação
        TestCase("context", "/start", is_reset=True),
        TestCase("context", "Cliente CTX B"),
        TestCase("context", "que tecido é melhor pro calorão daqui do Pará?",
                 ["algodão", "PV"]),
        TestCase("context", "qual malha mais fresca pro Norte do Brasil?",
                 ["algodão", "PV"]),
        TestCase("context", "no calor de Belém que camisa fica melhor?",
                 ["algodão", "PV"]),
        TestCase("context", "sublimação pode em algodão?",
                 ["não", "poliéster"]),
        TestCase("context", "posso sublimax em camiseta normal?",
                 ["não", "poliéster"]),
        TestCase("context", "pra sublimaçao que tecido uso?",
                 ["poliéster", "PV"]),
        # Bloco 3 — jaleco/bordado/geral
        TestCase("context", "/start", is_reset=True),
        TestCase("context", "Cliente CTX C"),
        TestCase("context", "jaleco pra clínica médica, qual indica?",
                 ["gabardine", "jaleco"]),
        TestCase("context", "qual jaleco aguenta mais lavagem?",
                 ["gabardine"]),
        TestCase("context", "diferença do jaleco de medico pro de estetica?",
                 ["gabardine"]),
        TestCase("context", "qto custa colocar logo no jaleco?",
                 ["4,50", "bordado"]),
        TestCase("context", "primeira vez que borda cobra a mais?",
                 ["60", "programação"]),
        TestCase("context", "arquivo AI serve pra fazer bordado?",
                 ["AI", "arte"]),
        TestCase("context", "piquet é melhor que algodão pra uniforme?",
                 ["piquet", "durabilidade"]),
    ],
    "orcamento": [
        TestCase("orcamento", "/start", is_reset=True),
        TestCase("orcamento", "Thiago Autotest"),
        # fluxo principal canonico
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
        # variações de trigger (cada uma com reset → user_id novo)
        TestCase("orcamento", "/start", is_reset=True),
        TestCase("orcamento", "Cliente Variação A"),
        TestCase("orcamento", "bora fazer um orçamento",
                 expected_keywords=["segmento", "uniforme"]),
        TestCase("orcamento", "/start", is_reset=True),
        TestCase("orcamento", "Cliente Variação B"),
        TestCase("orcamento", "quero cotar uns jaleco",
                 expected_keywords=["segmento", "uniforme"]),
        TestCase("orcamento", "/start", is_reset=True),
        TestCase("orcamento", "Cliente Variação C"),
        TestCase("orcamento", "me passa um orçamento pf",
                 expected_keywords=["segmento", "uniforme"]),
        # variações de segmento
        TestCase("orcamento", "/start", is_reset=True),
        TestCase("orcamento", "Cliente Segmento"),
        TestCase("orcamento", "quero fazer um orçamento"),
        TestCase("orcamento", "saude",
                 note="sem acento — bot deve aceitar"),
    ],
    "edge": [
        # Bloco 1 — originais + erros ortográficos
        TestCase("edge", "/start", is_reset=True),
        TestCase("edge", "Cliente Edge A"),
        TestCase("edge", "qual o preço do bitcoin?",
                 [], note="deve cair em fallback (sem 'bitcoin price')"),
        TestCase("edge", "aaaaaaaaa",
                 [], note="não pode crashar — qualquer resposta ok"),
        TestCase("edge", "qnto custo o jalceo?",
                 [], note="erro de digitação — qualquer resposta ok"),
        TestCase("edge", "vcs faz burdado?",
                 ["bordado"]),
        TestCase("edge", "qual o preco da camiça polo?",
                 ["polo", "45"]),
        # Bloco 2 — gibberish + emoji + longa
        TestCase("edge", "/start", is_reset=True),
        TestCase("edge", "Cliente Edge B"),
        TestCase("edge", "asdfghjkl",
                 [], note="gibberish — qualquer resposta ok"),
        TestCase("edge", "!!!!!!",
                 [], note="só pontuação — qualquer resposta ok"),
        TestCase("edge", "123456",
                 [], note="só números — qualquer resposta ok"),
        TestCase(
            "edge",
            "olá tudo bem eu quero saber sobre os preços de todos os "
            "produtos que vocês têm disponíveis incluindo polo jaleco "
            "camiseta bordado serigrafia sublimação e também quero saber "
            "sobre entrega e prazo obrigado",
            [],
            note="mensagem muito longa — não pode timeout",
        ),
        TestCase("edge", "👕",
                 [], note="emoji-only — qualquer resposta ok"),
        TestCase("edge", "💰❓",
                 [], note="emoji-only — qualquer resposta ok"),
    ],
}


# ── Pipeline factory ──────────────────────────────────────────────────────────


def build_pipeline(mock_llm: bool) -> MessagePipeline:
    campaign = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign.reload()
    faq = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign)

    llm_router = None
    context_engine = None

    if not mock_llm and settings.ANTHROPIC_API_KEY:
        import anthropic  # noqa: WPS433

        from app.engines.context_engine import ContextEngine
        from app.engines.llm_router import LLMRouter

        llm_client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )
        llm_router = LLMRouter(settings.LLM_CONFIG_PATH, client=llm_client)

        ctx_client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )
        context_engine = ContextEngine(
            knowledge_base_path=settings.KNOWLEDGE_BASE_PATH,
            products_path=Path("app/knowledge/products.json"),
            anthropic_client=ctx_client,
        )

    return MessagePipeline(
        faq_engine=faq,
        campaign_engine=campaign,
        llm_router=llm_router,
        context_engine=context_engine,
    )


# ── DB session ────────────────────────────────────────────────────────────────


def make_db_factory():
    db_url = settings.TEST_DATABASE_URL or settings.DATABASE_URL
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Conversation runner ───────────────────────────────────────────────────────


def evaluate(result: AutoTestResult, expected: list[str]) -> AutoTestResult:
    result.expected_keywords = expected
    text_lower = result.response.lower()
    result.found_keywords = [k for k in expected if k.lower() in text_lower]
    result.missing_keywords = [
        k for k in expected if k.lower() not in text_lower
    ]
    if expected:
        result.passed = not result.missing_keywords and not result.error
    else:
        # Sem keywords esperadas: passa se houve qualquer resposta sem erro
        result.passed = bool(result.response) and not result.error

    if result.error:
        result.layer_hint = "error"
    elif result.latency_ms < 500:
        result.layer_hint = "faq"
    elif result.latency_ms < 3000:
        result.layer_hint = "llm"
    else:
        result.layer_hint = "context"
    return result


async def run_suite(
    pipeline: MessagePipeline,
    session_factory,
    suite_name: str,
) -> list[AutoTestResult]:
    from datetime import timezone

    from app.schemas.messaging import InboundMessage

    cases = SUITES[suite_name]
    db = session_factory()
    user_id = f"AUTOTEST_{suite_name}_{uuid.uuid4().hex[:8]}"
    counter = 0
    results: list[AutoTestResult] = []

    try:
        for case in cases:
            if case.is_reset:
                # Nova sessão com user_id novo para resetar estado/rate limit
                user_id = f"AUTOTEST_{suite_name}_{uuid.uuid4().hex[:8]}"
                counter = 0

            counter += 1
            inbound = InboundMessage(
                channel_id="telegram",
                channel_message_id=(
                    f"autotest_{user_id}_{counter}_{int(time.time() * 1000)}"
                ),
                channel_user_id=user_id,
                display_name="AUTOTEST",
                content=case.message,
                timestamp=datetime.now(timezone.utc),
                raw_payload={"autotest": True, "text": case.message},
            )

            result = AutoTestResult(suite=suite_name, message=case.message)
            t0 = time.perf_counter()
            try:
                outbound = await pipeline.process(inbound, db)
                if outbound is not None:
                    result.response = outbound.response.get("body", "") or ""
            except Exception as exc:  # noqa: BLE001
                result.error = f"{type(exc).__name__}: {exc}"
                db.rollback()
            result.latency_ms = (time.perf_counter() - t0) * 1000

            evaluate(result, case.expected_keywords)
            print_result(result)
            results.append(result)
    finally:
        db.close()

    return results


def print_result(r: AutoTestResult) -> None:
    layer_label = {
        "faq": "FAQ",
        "llm": "LLM",
        "context": "CTX",
        "error": "ERR",
        "unknown": "  -",
    }.get(r.layer_hint, "  -")
    status = "✅" if r.passed else "❌"
    msg = r.message if len(r.message) <= 50 else r.message[:47] + "..."
    resp = r.response if len(r.response) <= 80 else r.response[:77] + "..."
    print(
        f"[{layer_label}] {status} {r.latency_ms:6.0f}ms  {msg!r:<55} "
        f"-> {resp!r}"
    )
    if r.missing_keywords:
        print(f"           missing: {r.missing_keywords}")
    if r.error:
        print(f"           ERROR: {r.error}")


# ── HTML report (reaproveitado do telegram_autotest.py) ───────────────────────


def render_html(results: list[AutoTestResult], generated_at: datetime) -> str:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    avg_latency = (
        sum(r.latency_ms for r in results) / total if total else 0.0
    )

    by_layer: dict[str, list[float]] = {"faq": [], "llm": [], "context": []}
    for r in results:
        if r.layer_hint in by_layer:
            by_layer[r.layer_hint].append(r.latency_ms)
    layer_avg = {
        k: (sum(v) / len(v) if v else 0.0) for k, v in by_layer.items()
    }

    rows = []
    for r in results:
        if r.error:
            badge = "slow"
        elif r.latency_ms < 500:
            badge = "ok"
        elif r.latency_ms < 3000:
            badge = "warn"
        else:
            badge = "slow"
        status = "✅" if r.passed else "❌"
        kw_html = (
            f"<span class='kw-ok'>✓ "
            f"{', '.join(html.escape(k) for k in r.found_keywords) or '—'}"
            f"</span><br>"
            f"<span class='kw-miss'>✗ "
            f"{', '.join(html.escape(k) for k in r.missing_keywords) or '—'}"
            f"</span>"
        )
        rows.append(
            f"<tr>"
            f"<td>{html.escape(r.suite)}</td>"
            f"<td><code>{html.escape(r.message)}</code></td>"
            f"<td>{html.escape(r.response[:200])}"
            f"{'…' if len(r.response) > 200 else ''}</td>"
            f"<td><span class='badge {badge}'>{r.latency_ms:.0f}ms</span></td>"
            f"<td>{status}</td>"
            f"<td>{kw_html}</td>"
            f"</tr>"
        )

    details_blocks = []
    for r in results:
        body = html.escape(r.response) or "<em>(sem resposta)</em>"
        if r.error:
            body += f"\n\nERROR: {html.escape(r.error)}"
        details_blocks.append(
            f"<details><summary>"
            f"[{html.escape(r.suite)}] "
            f"{html.escape(r.message)} ({r.latency_ms:.0f}ms)"
            f"</summary>"
            f"<pre>{body}</pre>"
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
<title>Camisart AI — Autotest {generated_at:%Y-%m-%d %H:%M}</title>
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
<h1>Camisart AI — Autotest (pipeline direto)</h1>
<div class="meta">Gerado em {generated_at:%Y-%m-%d %H:%M:%S}</div>

<div class="cards">
  <div class="card"><div class="label">Total</div><div class="value">{total}</div></div>
  <div class="card pass"><div class="label">✅ Passed</div><div class="value">{passed}</div></div>
  <div class="card fail"><div class="label">❌ Failed</div><div class="value">{failed}</div></div>
  <div class="card"><div class="label">Avg Latency</div><div class="value">{avg_latency:.0f}ms</div></div>
</div>

<h2>Latência média por camada</h2>
<div class="chart-wrap"><canvas id="latencyChart"></canvas></div>

<h2>Resultados</h2>
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


def export_html(results: list[AutoTestResult]) -> Path:
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
        description=(
            "Testes automáticos do bot via pipeline direto "
            "(sem Telegram)."
        ),
    )
    p.add_argument(
        "--suite", choices=suites, default="all",
        help="Suite a executar (default: all).",
    )
    p.add_argument(
        "--mock-llm", action="store_true",
        help="Não usa Claude API — apenas Camada 1 (FAQ regex).",
    )
    p.add_argument(
        "--export", action="store_true",
        help="Gera relatório HTML em docs/evaluation/reports/.",
    )
    return p.parse_args()


def print_summary(results: list[AutoTestResult]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pct = (passed / total * 100) if total else 0.0

    by_suite: dict[str, list[AutoTestResult]] = {}
    for r in results:
        by_suite.setdefault(r.suite, []).append(r)
    suite_status = []
    for name, items in by_suite.items():
        n_pass = sum(1 for r in items if r.passed)
        n_total = len(items)
        if n_pass == n_total:
            mark = "✅"
        elif n_pass == 0:
            mark = "❌"
        else:
            mark = "⚠️"
        suite_status.append(f"{name} {mark} ({n_pass}/{n_total})")

    by_layer: dict[str, list[float]] = {"faq": [], "llm": [], "context": []}
    for r in results:
        if r.layer_hint in by_layer:
            by_layer[r.layer_hint].append(r.latency_ms)
    layer_avgs = " · ".join(
        f"{k} {sum(v) / len(v):.0f}ms"
        for k, v in by_layer.items() if v
    ) or "(sem dados)"

    print()
    print("=" * 60)
    print(f"RESULTADO: {passed}/{total} passed ({pct:.1f}%)")
    print(f"Suites: {' '.join(suite_status)}")
    print(f"Latência média: {layer_avgs}")
    print("=" * 60)


async def amain() -> int:
    args = parse_args()

    if not (settings.TEST_DATABASE_URL or settings.DATABASE_URL):
        print(
            "ERRO: configure TEST_DATABASE_URL ou DATABASE_URL em .env",
            file=sys.stderr,
        )
        return 2

    pipeline = build_pipeline(mock_llm=args.mock_llm)
    session_factory = make_db_factory()

    if args.mock_llm:
        print(">>> mock-llm: somente Camada 1 (FAQ regex). <<<")
    elif not settings.ANTHROPIC_API_KEY:
        print(">>> ANTHROPIC_API_KEY ausente: somente Camada 1. <<<")
    else:
        print(">>> Camadas 2 e 3 ativas (Claude Haiku). <<<")

    suite_names = list(SUITES.keys()) if args.suite == "all" else [args.suite]

    all_results: list[AutoTestResult] = []
    for suite_name in suite_names:
        print(f"\n=== Suite: {suite_name} ===")
        results = await run_suite(pipeline, session_factory, suite_name)
        all_results.extend(results)

    print_summary(all_results)

    if args.export:
        path = export_html(all_results)
        print(f"\nRelatório HTML: {path}")

    failed = sum(1 for r in all_results if not r.passed)
    return 0 if failed == 0 else 1


def main() -> None:
    sys.exit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
