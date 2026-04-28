"""Registro de métricas de áudio em arquivo JSON local (JSONL).

Não usamos banco de dados aqui para manter a feature isolada e
não introduzir uma tabela só para telemetria leve.

Arquivo: ``docs/evaluation/audio_metrics.jsonl`` — uma linha JSON
por evento (formato JSONL).
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

METRICS_PATH = Path("docs/evaluation/audio_metrics.jsonl")


def record_audio_event(
    status: str,
    duration_ms: float,
    text_length: int = 0,
    intent_id: str = "",
    channel_user_id: str = "",
) -> None:
    """Registra um evento de áudio no arquivo de métricas.

    Args:
        status: ``"success"`` | ``"failed"`` | ``"no_service"``
        duration_ms: tempo de transcrição em milissegundos
        text_length: chars do texto transcrito (0 se falhou)
        intent_id: intent identificado após transcrição (se houver)
        channel_user_id: identificador do usuário no canal
    """
    try:
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "duration_ms": round(duration_ms, 1),
            "text_length": text_length,
            "intent_id": intent_id,
            "channel_user_id": channel_user_id,
        }
        with open(METRICS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("audio_metrics: falha ao registrar evento: %s", exc)


def load_audio_metrics() -> list[dict]:
    """Carrega todos os eventos de áudio registrados."""
    if not METRICS_PATH.exists():
        return []
    events: list[dict] = []
    with open(METRICS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def compute_audio_stats(events: list[dict]) -> dict:
    """Calcula estatísticas dos eventos de áudio.

    Retorna ``{"total","success","failed","success_rate",
    "avg_duration_ms","avg_text_length","top_intents","by_day"}``.
    """
    if not events:
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "success_rate": 0.0,
            "avg_duration_ms": 0.0,
            "avg_text_length": 0,
            "top_intents": [],
            "by_day": [],
        }

    total = len(events)
    success = sum(1 for e in events if e.get("status") == "success")
    failed = total - success
    success_rate = round(success / total * 100, 1) if total else 0.0

    durations = [
        e["duration_ms"] for e in events if e.get("status") == "success"
    ]
    avg_duration = round(sum(durations) / len(durations), 0) if durations else 0

    lengths = [e["text_length"] for e in events if e.get("text_length", 0) > 0]
    avg_length = round(sum(lengths) / len(lengths), 0) if lengths else 0

    intents = [
        e["intent_id"]
        for e in events
        if e.get("intent_id") and e.get("status") == "success"
    ]
    top_intents = [
        {"intent": k, "count": v}
        for k, v in Counter(intents).most_common(5)
    ]

    by_day_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"success": 0, "failed": 0}
    )
    for e in events:
        day = (e.get("ts") or "")[:10]
        if not day:
            continue
        status = e.get("status", "")
        # "no_service" também é uma falha do ponto de vista do usuário
        if status == "success":
            by_day_counts[day]["success"] += 1
        else:
            by_day_counts[day]["failed"] += 1
    by_day = [
        {"day": k, **v}
        for k, v in sorted(by_day_counts.items())[-7:]
    ]

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "success_rate": success_rate,
        "avg_duration_ms": avg_duration,
        "avg_text_length": avg_length,
        "top_intents": top_intents,
        "by_day": by_day,
    }
