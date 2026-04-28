"""Seed de métricas de áudio para demonstração.

Gera eventos realistas dos últimos 7 dias e grava no JSONL.
Substitui qualquer arquivo anterior — uso apenas em ambiente de demo.

Uso:
    python scripts/seed_audio_metrics.py
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


METRICS_PATH = Path("docs/evaluation/audio_metrics.jsonl")

INTENTS = [
    "preco_polo",
    "preco_jaleco",
    "orcamento_trigger",
    "bordado_prazo",
    "segmento_negocio",
    "pedido_minimo",
    "pagamento",
    "prazo_entrega",
]


def main() -> None:
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []
    now = datetime.now(timezone.utc)

    for day_offset in range(7, 0, -1):
        day = now - timedelta(days=day_offset)
        n_audio = random.randint(3, 12)
        for _ in range(n_audio):
            success = random.random() > 0.08  # 92% taxa de sucesso
            hour = random.randint(8, 18)
            ts = day.replace(
                hour=hour,
                minute=random.randint(0, 59),
                second=0,
                microsecond=0,
            )
            duration = (
                round(random.gauss(1800, 400), 1)
                if success
                else round(random.gauss(500, 100), 1)
            )
            events.append({
                "ts": ts.isoformat(),
                "status": "success" if success else "failed",
                "duration_ms": max(duration, 50.0),
                "text_length": random.randint(20, 120) if success else 0,
                "intent_id": random.choice(INTENTS) if success else "",
                "channel_user_id": f"user_{random.randint(1000, 9999)}",
            })

    events.sort(key=lambda e: e["ts"])

    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    total = len(events)
    success = sum(1 for e in events if e["status"] == "success")
    print(
        f"Seed criado: {total} eventos "
        f"({success} sucesso, {total - success} falha)"
    )
    print(f"Arquivo: {METRICS_PATH}")


if __name__ == "__main__":
    main()
