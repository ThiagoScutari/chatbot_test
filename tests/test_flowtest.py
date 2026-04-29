"""Tests for the flowtest module — no external API calls."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scripts.flowtest.flowtest_runner import (
    distribute_rounds,
    load_flows,
    load_personas,
)
from scripts.flowtest.models import FlowTestResult, PipelineResponse, Turn


PERSONAS_DIR = Path("scripts/flowtest/personas")
FLOWS_DIR = Path("scripts/flowtest/flows")


def test_load_all_personas() -> None:
    """All 5 persona docs load successfully."""
    personas = load_personas()
    assert len(personas) == 5
    expected = {"dona_raimunda", "seu_carlos", "jessica", "tiago", "dona_maria"}
    assert set(personas.keys()) == expected


def test_load_persona_filter() -> None:
    """--persona filter returns only one."""
    personas = load_personas(filter_persona="jessica")
    assert len(personas) == 1
    assert "jessica" in personas


def test_load_all_flows() -> None:
    """All 7 flow docs load with weight and max_turns."""
    flows = load_flows()
    assert len(flows) == 7
    for f in flows:
        assert "name" in f
        assert "weight" in f
        assert "max_turns" in f
        assert f["weight"] > 0
        assert f["max_turns"] > 0


def test_flow_weights_sum() -> None:
    """Flow weights sum to 100."""
    flows = load_flows()
    total = sum(f["weight"] for f in flows)
    assert total == 100


def test_distribute_rounds_total() -> None:
    """Total assignments equals requested rounds."""
    personas = load_personas()
    flows = load_flows()
    assignments = distribute_rounds(list(personas.keys()), flows, 25, seed=42)
    assert len(assignments) == 25


def test_distribute_rounds_equal_personas() -> None:
    """Each persona gets equal rounds (±1 for remainder)."""
    personas = load_personas()
    flows = load_flows()
    assignments = distribute_rounds(list(personas.keys()), flows, 25, seed=42)
    counts = Counter(a["persona"] for a in assignments)
    assert all(c == 5 for c in counts.values())


def test_distribute_rounds_remainder() -> None:
    """27 rounds / 5 personas handles remainder correctly."""
    personas = load_personas()
    flows = load_flows()
    assignments = distribute_rounds(list(personas.keys()), flows, 27, seed=42)
    assert len(assignments) == 27
    counts = Counter(a["persona"] for a in assignments)
    assert sorted(counts.values()) == [5, 5, 5, 6, 6]


def test_distribute_rounds_weighted_flows() -> None:
    """Flow distribution approximately matches weights over many rounds."""
    personas = load_personas()
    flows = load_flows()
    assignments = distribute_rounds(
        list(personas.keys()), flows, 1000, seed=42
    )
    flow_counts = Counter(a["flow"] for a in assignments)
    # compra (weight 40) should be ~400 ±60
    assert 340 <= flow_counts.get("compra", 0) <= 460
    # fora_contexto (weight 5) should be ~50 ±30
    assert 20 <= flow_counts.get("fora_contexto", 0) <= 80


def test_distribute_rounds_seed_reproducible() -> None:
    """Same seed produces same distribution."""
    personas = load_personas()
    flows = load_flows()
    a1 = distribute_rounds(list(personas.keys()), flows, 25, seed=42)
    a2 = distribute_rounds(list(personas.keys()), flows, 25, seed=42)
    assert a1 == a2


def test_distribute_rounds_different_seeds() -> None:
    """Different seeds produce different distributions."""
    personas = load_personas()
    flows = load_flows()
    a1 = distribute_rounds(list(personas.keys()), flows, 25, seed=42)
    a2 = distribute_rounds(list(personas.keys()), flows, 25, seed=99)
    assert a1 != a2


def test_persona_docs_have_required_sections() -> None:
    """Every persona doc has mandatory sections."""
    required = [
        "## Perfil",
        "## Comportamento linguístico",
        "## Regras para o agente",
    ]
    for f in PERSONAS_DIR.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        for section in required:
            assert section in content, f"{f.name} missing '{section}'"


def test_flow_docs_have_required_sections() -> None:
    """Every flow doc has mandatory sections."""
    required = ["## Peso", "## Objetivo", "## Máximo de turnos"]
    for f in FLOWS_DIR.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        for section in required:
            assert section in content, f"{f.name} missing '{section}'"


def test_flowtest_result_serialization() -> None:
    """FlowTestResult converts to dict/JSON correctly."""
    result = FlowTestResult(
        interaction_id="test_001",
        persona="dona_raimunda",
        flow="compra",
        turns=[Turn(0, "/start", "Olá!", "start_command", 2)],
        total_turns=1,
        completed=True,
        total_latency_ms=2,
    )
    data = result.to_dict()
    assert data["persona"] == "dona_raimunda"
    assert data["flow"] == "compra"
    assert len(data["turns"]) == 1
    json_str = json.dumps(data, ensure_ascii=False)
    assert "dona_raimunda" in json_str


def test_pipeline_response_dataclass() -> None:
    """PipelineResponse stores fields correctly."""
    resp = PipelineResponse(text="Olá!", intent_id="start_command", latency_ms=5)
    assert resp.text == "Olá!"
    assert resp.intent_id == "start_command"
    assert resp.latency_ms == 5
