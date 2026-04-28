"""
Avalia o desempenho do Camisart AI contra o dataset rotulado.

Métricas: Accuracy, Precision, Recall, F1, Matriz de Confusão, Latência.

Uso:
    python scripts/evaluate.py
    python scripts/evaluate.py --layer faq
    python scripts/evaluate.py --difficulty hard
    python scripts/evaluate.py --export
    python scripts/evaluate.py --no-llm   (só Camada 1 — mais rápido)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

DATASET_PATH = Path("docs/evaluation/dataset.json")
REPORTS_DIR = Path("docs/evaluation/reports")


@dataclass
class EvalResult:
    sample_id: str
    message: str
    expected: str
    predicted: str
    expected_layer: str
    actual_layer: str  # "faq" | "llm" | "rag" | "none"
    correct: bool
    latency_ms: float
    difficulty: str


@dataclass
class EvalReport:
    timestamp: str
    total_samples: int
    accuracy: float
    f1_macro: float
    precision_per_intent: dict
    recall_per_intent: dict
    f1_per_intent: dict
    support_per_intent: dict
    confusion_matrix: list
    confusion_labels: list
    accuracy_by_layer: dict
    accuracy_by_difficulty: dict
    fallback_rate: float
    avg_latency_by_layer: dict
    top_errors: list
    results: list = field(default_factory=list)


def _predict_with_faq_only(message: str, faq_engine) -> tuple[str, str]:
    """Predição usando apenas Camada 1 (FAQ regex). Retorna (intent_id, layer)."""
    match = faq_engine.match(message)
    if match:
        return match.intent_id, "faq"
    return "none", "none"


async def _predict_full(
    message: str,
    faq_engine,
    llm_router,
    thresholds: dict,
    context_engine=None,
) -> tuple[str, str]:
    """Predição Camadas 1+2+3 com Camada 3 prioritária para perguntas
    técnicas [fix-C1]. Retorna (intent_id, layer)."""
    from app.engines.rag_engine import is_product_question

    match = faq_engine.match(message)
    if match:
        return match.intent_id, "faq"

    # Camada 3 prioritária: pergunta técnica vai direto ao ContextEngine,
    # antes do LLM. Reduz casos onde LLM classifica produto-pergunta como
    # falar_humano/preco_jaleco com confiança ≥ medium.
    if context_engine and is_product_question(message):
        ctx_result = await context_engine.answer(message)
        if ctx_result.answer:
            return "context_response", "context"

    if llm_router:
        known = faq_engine.intent_ids()
        clf = await llm_router.classify_intent(message, {}, known)
        if clf.intent_id and clf.confidence >= thresholds.get("medium", 0.60):
            return clf.intent_id, "llm"

    return "none", "none"


def compute_report(results: list[EvalResult]) -> EvalReport:
    y_true = [r.expected for r in results]
    y_pred = [r.predicted for r in results]
    labels = sorted(set(y_true + y_pred))

    accuracy = accuracy_score(y_true, y_pred)

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        average=None,
        zero_division=0,
    )
    _, _, f1_macro, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )

    cm = confusion_matrix(y_true, y_pred, labels=labels)

    by_layer = defaultdict(list)
    for r in results:
        by_layer[r.expected_layer].append(r.correct)
    acc_by_layer = {k: sum(v) / len(v) for k, v in by_layer.items()}

    by_diff = defaultdict(list)
    for r in results:
        by_diff[r.difficulty].append(r.correct)
    acc_by_diff = {k: sum(v) / len(v) for k, v in by_diff.items()}

    false_fallbacks = [
        r for r in results if r.predicted == "none" and r.expected != "none"
    ]
    non_none = [r for r in results if r.expected != "none"]
    fallback_rate = len(false_fallbacks) / len(non_none) if non_none else 0

    lat_by_layer = defaultdict(list)
    for r in results:
        lat_by_layer[r.actual_layer].append(r.latency_ms)
    avg_lat = {k: sum(v) / len(v) for k, v in lat_by_layer.items()}

    error_counter = Counter(
        (r.expected, r.predicted) for r in results if not r.correct
    )
    top_errors = [
        {
            "expected": exp,
            "predicted": pred,
            "count": count,
            "examples": [
                r.message
                for r in results
                if r.expected == exp and r.predicted == pred
            ][:3],
        }
        for (exp, pred), count in error_counter.most_common(10)
    ]

    return EvalReport(
        timestamp=datetime.now().isoformat(),
        total_samples=len(results),
        accuracy=float(accuracy),
        f1_macro=float(f1_macro),
        precision_per_intent=dict(zip(labels, [float(x) for x in precision])),
        recall_per_intent=dict(zip(labels, [float(x) for x in recall])),
        f1_per_intent=dict(zip(labels, [float(x) for x in f1])),
        support_per_intent=dict(zip(labels, [int(x) for x in support])),
        confusion_matrix=cm.tolist(),
        confusion_labels=labels,
        accuracy_by_layer=acc_by_layer,
        accuracy_by_difficulty=acc_by_diff,
        fallback_rate=float(fallback_rate),
        avg_latency_by_layer=avg_lat,
        top_errors=top_errors,
        results=[asdict(r) for r in results],
    )


def print_report(report: EvalReport) -> None:
    """Imprime relatório formatado no terminal."""
    W = 68
    print()
    print("=" * W)
    print("CAMISART AI - AVALIACAO DE DESEMPENHO")
    print(
        f"Data: {report.timestamp[:10]} | "
        f"Dataset: {report.total_samples} amostras"
    )
    print("=" * W)

    def bar(v, width=20):
        filled = int(v * width)
        return "#" * filled + "." * (width - filled)

    def grade(v):
        if v >= 0.95:
            return "Excelente"
        if v >= 0.85:
            return "Bom"
        if v >= 0.75:
            return "Regular"
        return "Precisa melhorar"

    print()
    print("RESUMO EXECUTIVO")
    print("-" * W)
    print(
        f"  Accuracy global:     {report.accuracy * 100:5.1f}%  "
        f"{bar(report.accuracy)}  {grade(report.accuracy)}"
    )
    print(
        f"  F1 macro:            {report.f1_macro * 100:5.1f}%  "
        f"{bar(report.f1_macro)}  {grade(report.f1_macro)}"
    )
    fallback_tag = "Otimo" if report.fallback_rate < 0.10 else "Alto"
    print(
        f"  Fallback indevido:   {report.fallback_rate * 100:5.1f}%  "
        f"{fallback_tag}"
    )

    for layer, lat in sorted(report.avg_latency_by_layer.items()):
        print(f"  Latencia {layer:8s}:  {lat:6.0f}ms")

    print()
    print("POR CAMADA")
    print("-" * W)
    for layer, acc in sorted(report.accuracy_by_layer.items()):
        print(f"  {layer:8s}: Accuracy {acc * 100:5.1f}%  {bar(acc)}")

    print()
    print("POR DIFICULDADE")
    print("-" * W)
    for diff in ["easy", "medium", "hard"]:
        if diff in report.accuracy_by_difficulty:
            acc = report.accuracy_by_difficulty[diff]
            label = {"easy": "Facil  ", "medium": "Medio  ", "hard": "Dificil"}[diff]
            print(f"  {label}: {acc * 100:5.1f}%  {bar(acc)}")

    print()
    print("F1 POR INTENT")
    print("-" * W)
    sorted_intents = sorted(
        report.f1_per_intent.items(), key=lambda x: x[1], reverse=True
    )
    for intent, f1 in sorted_intents:
        sup = report.support_per_intent.get(intent, 0)
        print(f"  {intent:28s} {bar(f1, 16)} {f1 * 100:5.1f}%  (n={sup})")

    if report.top_errors:
        print()
        print("ERROS MAIS FREQUENTES")
        print("-" * W)
        for i, err in enumerate(report.top_errors[:5], 1):
            print(
                f"  {i}. [{err['count']:2d}x] "
                f"{err['expected']:20s} -> {err['predicted']}"
            )
            for ex in err["examples"][:2]:
                print(f"       \"{ex[:55]}\"")

    print()
    print("=" * W)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--layer",
        choices=["faq", "llm", "rag", "none"],
        help="Filtrar por camada esperada",
    )
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        help="Filtrar por dificuldade",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Salvar relatorio JSON para o dashboard",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Usar apenas Camada 1 (mais rapido)",
    )
    parser.add_argument(
        "--output",
        help=(
            "Nome base do relatório (ex: 2026-04-28_manual). "
            "Default: data atual (YYYY-MM-DD)."
        ),
        default=None,
    )
    args = parser.parse_args()

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    samples = dataset["samples"]

    if args.layer:
        samples = [s for s in samples if s["expected_layer"] == args.layer]
    if args.difficulty:
        samples = [s for s in samples if s["difficulty"] == args.difficulty]

    if not samples:
        print("Nenhuma amostra apos filtros.")
        return

    msg = f"Avaliando {len(samples)} amostras"
    if args.layer:
        msg += f" [layer={args.layer}]"
    if args.difficulty:
        msg += f" [difficulty={args.difficulty}]"
    if args.no_llm:
        msg += " [FAQ only]"
    print(msg + "...")

    from app.config import settings
    from app.engines.campaign_engine import CampaignEngine
    from app.engines.regex_engine import FAQEngine

    campaign = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign.reload()
    faq = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign)

    llm_router = None
    context_engine = None
    thresholds: dict[str, float] = {}
    if not args.no_llm and settings.ANTHROPIC_API_KEY:
        import anthropic

        from app.engines.context_engine import ContextEngine
        from app.engines.llm_router import LLMRouter

        llm_config = json.loads(
            settings.LLM_CONFIG_PATH.read_text(encoding="utf-8")
        )
        thresholds = {
            k: v for k, v in llm_config.get("thresholds", {}).items()
        }
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        llm_router = LLMRouter(settings.LLM_CONFIG_PATH, client=client)
        print(
            f"LLMRouter ativo (Claude Haiku). "
            f"Estimativa: ~{len(samples) * 2}s"
        )

        ctx_client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )
        context_engine = ContextEngine(
            knowledge_base_path=settings.KNOWLEDGE_BASE_PATH,
            products_path=Path("app/knowledge/products.json"),
            anthropic_client=ctx_client,
        )
        print(
            f"ContextEngine ativo "
            f"(~{context_engine.estimated_tokens()} tokens)."
        )

    results = []
    for i, sample in enumerate(samples, 1):
        if i % 20 == 0:
            print(f"  {i}/{len(samples)}...")

        start = time.perf_counter()
        if args.no_llm or not llm_router:
            predicted, layer = _predict_with_faq_only(sample["message"], faq)
        else:
            predicted, layer = await _predict_full(
                sample["message"],
                faq,
                llm_router,
                thresholds,
                context_engine=context_engine,
            )
        latency = (time.perf_counter() - start) * 1000

        results.append(
            EvalResult(
                sample_id=sample["id"],
                message=sample["message"],
                expected=sample["expected_intent"],
                predicted=predicted,
                expected_layer=sample["expected_layer"],
                actual_layer=layer,
                correct=(predicted == sample["expected_intent"]),
                latency_ms=latency,
                difficulty=sample.get("difficulty", "medium"),
            )
        )

    report = compute_report(results)
    print_report(report)

    if args.export:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        base_name = args.output or datetime.now().strftime("%Y-%m-%d")
        report_path = REPORTS_DIR / f"{base_name}_report.json"
        report_dict = asdict(report)
        report_path.write_text(
            json.dumps(report_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nRelatorio salvo em: {report_path}")
        print(
            "Para gerar o dashboard: "
            f"python scripts/dashboard.py --output {base_name}"
        )


if __name__ == "__main__":
    asyncio.run(main())
