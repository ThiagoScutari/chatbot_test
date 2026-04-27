"""Testes do pipeline de avaliação (Sprint 08)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATASET_PATH = Path("docs/evaluation/dataset.json")


def load_dataset():
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def get_valid_intents():
    faq = json.loads(
        Path("app/knowledge/faq.json").read_text(encoding="utf-8")
    )
    ids = {i["id"] for i in faq["intents"]}
    ids.add("none")
    ids.add("rag_response")
    return ids


# ── Dataset structure ───────────────────────────────────────────────


def test_dataset_existe():
    assert DATASET_PATH.exists(), (
        "docs/evaluation/dataset.json não encontrado"
    )


def test_dataset_tem_amostras_minimas():
    data = load_dataset()
    assert len(data["samples"]) >= 200, (
        f"Esperado >=200 amostras, encontrado {len(data['samples'])}"
    )


def test_dataset_campos_obrigatorios():
    data = load_dataset()
    for sample in data["samples"]:
        for field in (
            "id",
            "message",
            "expected_intent",
            "expected_layer",
            "difficulty",
        ):
            assert field in sample, (
                f"Campo '{field}' ausente em amostra {sample.get('id')}"
            )


def test_dataset_intents_validos():
    data = load_dataset()
    valid = get_valid_intents()
    for sample in data["samples"]:
        assert sample["expected_intent"] in valid, (
            f"Intent inválido '{sample['expected_intent']}' "
            f"em amostra {sample['id']}"
        )


def test_dataset_dificuldades_validas():
    data = load_dataset()
    for sample in data["samples"]:
        assert sample["difficulty"] in ("easy", "medium", "hard"), (
            f"Dificuldade inválida em {sample['id']}"
        )


def test_dataset_ids_unicos():
    data = load_dataset()
    ids = [s["id"] for s in data["samples"]]
    assert len(ids) == len(set(ids)), "IDs duplicados no dataset"


def test_dataset_mensagens_nao_vazias():
    data = load_dataset()
    for sample in data["samples"]:
        assert len(sample["message"].strip()) > 3, (
            f"Mensagem vazia ou muito curta em {sample['id']}"
        )


def test_dataset_distribuicao_minima_por_intent():
    data = load_dataset()
    counts = Counter(s["expected_intent"] for s in data["samples"])
    for intent, count in counts.items():
        assert count >= 9, (
            f"Intent '{intent}' tem apenas {count} amostras (mínimo 9)"
        )


def test_dataset_tem_todas_dificuldades():
    data = load_dataset()
    diffs = {s["difficulty"] for s in data["samples"]}
    assert diffs == {"easy", "medium", "hard"}


# ── compute_report ──────────────────────────────────────────────────


def test_compute_report_accuracy_correta():
    from scripts.evaluate import EvalResult, compute_report

    results = [
        EvalResult(
            "S1", "msg", "polo", "polo", "faq", "faq", True, 1.0, "easy"
        )
        for _ in range(9)
    ]
    results.append(
        EvalResult(
            "S10", "msg", "polo", "none", "faq", "none", False, 1.0, "easy"
        )
    )
    report = compute_report(results)
    assert abs(report.accuracy - 0.9) < 0.01


def test_compute_report_fallback_rate():
    from scripts.evaluate import EvalResult, compute_report

    results = [
        EvalResult(
            "S1", "msg", "polo", "polo", "faq", "faq", True, 1.0, "easy"
        ),
        EvalResult(
            "S2", "msg", "polo", "none", "faq", "none", False, 1.0, "easy"
        ),
        EvalResult(
            "S3", "msg", "none", "none", "none", "none", True, 1.0, "easy"
        ),
    ]
    report = compute_report(results)
    # 1 false fallback em 2 amostras não-none = 50%
    assert abs(report.fallback_rate - 0.5) < 0.01


def test_compute_report_confusion_matrix_shape():
    from scripts.evaluate import EvalResult, compute_report

    results = [
        EvalResult(
            "S1", "m", "polo", "polo", "faq", "faq", True, 1.0, "easy"
        ),
        EvalResult(
            "S2", "m", "polo", "jaleco", "faq", "faq", False, 1.0, "easy"
        ),
        EvalResult(
            "S3", "m", "jaleco", "jaleco", "faq", "faq", True, 1.0, "easy"
        ),
    ]
    report = compute_report(results)
    n = len(report.confusion_labels)
    assert len(report.confusion_matrix) == n
    assert all(len(row) == n for row in report.confusion_matrix)


# ── Dashboard ───────────────────────────────────────────────────────


def test_dashboard_gera_html(tmp_path):
    from scripts.dashboard import generate_dashboard

    fake_report = {
        "timestamp": "2026-04-23T10:00:00",
        "total_samples": 10,
        "accuracy": 0.9,
        "f1_macro": 0.88,
        "fallback_rate": 0.05,
        "f1_per_intent": {"polo": 0.95, "none": 0.90},
        "precision_per_intent": {"polo": 0.95, "none": 0.90},
        "recall_per_intent": {"polo": 0.95, "none": 0.90},
        "support_per_intent": {"polo": 6, "none": 4},
        "confusion_matrix": [[5, 1], [0, 4]],
        "confusion_labels": ["polo", "none"],
        "accuracy_by_layer": {"faq": 0.97, "llm": 0.88},
        "accuracy_by_difficulty": {
            "easy": 0.99,
            "medium": 0.94,
            "hard": 0.87,
        },
        "avg_latency_by_layer": {"faq": 0.8, "llm": 1842},
        "top_errors": [],
        "results": [],
    }
    out = tmp_path / "test_dashboard.html"
    generate_dashboard(fake_report, out)

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Camisart AI" in content
    assert "chart.js" in content.lower()
    assert "Analise Executiva" in content
    assert "90.0" in content  # accuracy = 0.9 -> 90.0%


def test_dashboard_contem_secoes_obrigatorias(tmp_path):
    from scripts.dashboard import generate_dashboard

    fake_report = {
        "timestamp": "2026-04-23T10:00:00",
        "total_samples": 5,
        "accuracy": 0.8,
        "f1_macro": 0.78,
        "fallback_rate": 0.10,
        "f1_per_intent": {"polo": 0.85},
        "precision_per_intent": {"polo": 0.85},
        "recall_per_intent": {"polo": 0.85},
        "support_per_intent": {"polo": 5},
        "confusion_matrix": [[4]],
        "confusion_labels": ["polo"],
        "accuracy_by_layer": {"faq": 0.9},
        "accuracy_by_difficulty": {"easy": 0.9},
        "avg_latency_by_layer": {"faq": 1.0},
        "top_errors": [],
        "results": [],
    }
    out = tmp_path / "test.html"
    generate_dashboard(fake_report, out)
    content = out.read_text(encoding="utf-8")

    for section in [
        "F1 Score por Intencao",
        "Precision vs Recall",
        "Distribuicao por Camada",
        "Acertos por Tipo de Pergunta",
        "Erros Mais Frequentes",
    ]:
        assert section in content, (
            f"Seção '{section}' ausente no dashboard"
        )
