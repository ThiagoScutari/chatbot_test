"""Analisa fallback rate no banco de dados.

Compara mensagens resolvidas pelo FAQ (matched_intent_id NOT NULL)
vs não resolvidas (NULL).

Uso:
    python scripts/llm_coverage_check.py
    python scripts/llm_coverage_check.py --days 7
    python scripts/llm_coverage_check.py --show-gaps
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import ProgrammingError  # noqa: E402

from app.database import SessionLocal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--show-gaps",
        action="store_true",
        help="Mostra mensagens que cairam em fallback",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        try:
            row = db.execute(
                text(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE matched_intent_id IS NOT NULL) AS matched,
                      COUNT(*) FILTER (WHERE matched_intent_id IS NULL) AS fallback,
                      COUNT(*) AS total
                    FROM messages
                    WHERE direction = 'in'
                      AND created_at >= NOW() - make_interval(days => :days)
                    """
                ),
                {"days": args.days},
            ).fetchone()
        except ProgrammingError as exc:
            db.rollback()
            if "does not exist" in str(exc):
                print(
                    "Tabela 'messages' não existe no banco configurado. "
                    "Rode as migrations antes: python app/migrations/migrate_sprint_03.py"
                )
                return
            raise

        matched, fallback, total = row  # type: ignore[misc]
        if total == 0:
            print(f"Nenhuma mensagem nos últimos {args.days} dias.")
            return

        faq_rate = matched * 100 / total
        fallback_rate = fallback * 100 / total

        print(f"\n{'=' * 55}")
        print(f"FAQ COVERAGE — últimos {args.days} dias")
        print(f"{'=' * 55}")
        print(f"  ✅ FAQ resolveu:   {matched:4d} msgs ({faq_rate:.1f}%)")
        print(f"  🤖 LLM necessário: {fallback:4d} msgs ({fallback_rate:.1f}%)")
        print(f"  Total:             {total:4d} msgs")
        print("\n  Meta: fallback < 20%")
        if fallback_rate < 20:
            status = "✅ OK"
        elif fallback_rate < 35:
            status = "⚠️  ATENÇÃO"
        else:
            status = "🔴 CRÍTICO — retreinar FAQ"
        print(f"  Status: {status}")

        if args.show_gaps and fallback > 0:
            gaps = db.execute(
                text(
                    """
                    SELECT content, COUNT(*) AS freq
                    FROM messages
                    WHERE direction = 'in'
                      AND matched_intent_id IS NULL
                      AND created_at >= NOW() - make_interval(days => :days)
                    GROUP BY content
                    ORDER BY freq DESC
                    LIMIT 20
                    """
                ),
                {"days": args.days},
            ).fetchall()

            print(f"\n{'─' * 55}")
            print(f"Top {len(gaps)} mensagens sem match no FAQ:")
            for msg, freq in gaps:
                print(f"  [{freq:3d}x] {msg[:60]!r}")

        print(f"{'=' * 55}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
