"""
Avaliacao qualitativa do Camisart AI.
Voce avalia N conversas em 5 dimensoes (escala 1-5).
Gera score qualitativo 0-100.

Uso:
    python scripts/qualitative_eval.py
    python scripts/qualitative_eval.py --sample 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DIMENSIONS = [
    ("precisao", "A resposta esta CORRETA?"),
    ("completude", "Cobre tudo que o cliente precisava?"),
    ("tom", "Tom adequado para loja de uniformes?"),
    ("clareza", "Facil de entender?"),
    ("acao", "Cliente saberia o que fazer depois?"),
]
QUAL_DIR = Path("docs/evaluation/qualitative")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=15)
    args = parser.parse_args()

    from app.config import settings
    from app.engines.campaign_engine import CampaignEngine
    from app.engines.regex_engine import FAQEngine
    from app.engines.state_machine import handle

    campaign = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign.reload()
    faq = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign)

    dataset = json.loads(
        Path("docs/evaluation/dataset.json").read_text(encoding="utf-8")
    )
    samples = random.sample(
        dataset["samples"], min(args.sample, len(dataset["samples"]))
    )

    print(f"\n{'=' * 60}")
    print(f"AVALIACAO QUALITATIVA - {len(samples)} conversas")
    print("Para cada resposta do bot, de notas de 1 a 5.")
    print(f"{'=' * 60}\n")

    eval_results = []
    for i, sample in enumerate(samples, 1):
        session = MagicMock()
        session.current_state = "menu"
        session.nome_cliente = "Cliente"
        session.session_data = {}
        session.last_interaction_at = None

        result = handle(sample["message"], session, faq)
        response = result.response.body if result.response else "(sem resposta)"

        print(f"\n[{i}/{len(samples)}] {'-' * 50}")
        print(f"CLIENTE: {sample['message']}")
        print(f"BOT:     {response[:200]}")
        print()

        scores = {}
        for dim_key, dim_label in DIMENSIONS:
            while True:
                try:
                    val = input(f"  {dim_label} [1-5]: ").strip()
                    score = int(val)
                    if 1 <= score <= 5:
                        scores[dim_key] = score
                        break
                    print("  Digite um numero entre 1 e 5.")
                except (ValueError, KeyboardInterrupt):
                    print("\nAvaliacao encerrada.")
                    return

        avg = sum(scores.values()) / len(scores)
        eval_results.append(
            {
                "sample_id": sample["id"],
                "message": sample["message"],
                "response": response,
                "scores": scores,
                "avg_score": round(avg, 2),
            }
        )

    overall = sum(r["avg_score"] for r in eval_results) / len(eval_results)
    score_100 = round(overall * 20, 1)

    dim_scores = {}
    for dim_key, _ in DIMENSIONS:
        vals = [r["scores"][dim_key] for r in eval_results]
        dim_scores[dim_key] = round(sum(vals) / len(vals) * 20, 1)

    print(f"\n{'=' * 60}")
    print("RESULTADO DA AVALIACAO QUALITATIVA")
    print(f"{'=' * 60}")
    print(f"  Score global: {score_100}/100")
    print()
    for dim_key, dim_label in DIMENSIONS:
        s = dim_scores.get(dim_key, 0)
        bar = "#" * int(s / 5) + "." * (20 - int(s / 5))
        print(f"  {dim_label[:35]:35s} {bar} {s:.0f}/100")

    grade = (
        "Excelente"
        if score_100 >= 85
        else "Bom"
        if score_100 >= 75
        else "Regular"
        if score_100 >= 65
        else "Precisa melhorar"
    )
    print(f"\n  Classificacao: {grade}")
    print(f"{'=' * 60}\n")

    QUAL_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "timestamp": datetime.now().isoformat(),
        "total_evaluated": len(eval_results),
        "score_global": score_100,
        "score_by_dimension": dim_scores,
        "grade": grade,
        "results": eval_results,
    }
    out_path = QUAL_DIR / f"{datetime.now():%Y-%m-%d}_qualitative.json"
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Resultado salvo em: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
