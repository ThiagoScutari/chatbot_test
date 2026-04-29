"""FlowTest CLI — multi-turn persona-driven conversation testing.

Usage:
    python -m scripts.flowtest                       # default: 25 rounds
    python -m scripts.flowtest --rounds 50
    python -m scripts.flowtest --persona jessica
    python -m scripts.flowtest --flow compra
    python -m scripts.flowtest --seed 42 --export
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

# Ensure we can import app.* when invoked as `python -m scripts.flowtest`
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# UTF-8 output on Windows terminals (cp1252 cannot print emojis).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

load_dotenv()

# Pipeline imports — must come after sys.path tweak.
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.engines.campaign_engine import CampaignEngine  # noqa: E402
from app.engines.regex_engine import FAQEngine  # noqa: E402
from app.pipeline.message_pipeline import MessagePipeline  # noqa: E402

# Register models on Base.metadata so create_all sees them.
import app.models.session  # noqa: E402, F401
import app.models.message  # noqa: E402, F401
import app.models.lead  # noqa: E402, F401
import app.models.audit_log  # noqa: E402, F401
import app.models.knowledge_chunk  # noqa: E402, F401

from scripts.flowtest.flowtest_report import generate_report  # noqa: E402
from scripts.flowtest.flowtest_runner import (  # noqa: E402
    distribute_rounds,
    load_flows,
    load_personas,
    run_single_interaction,
)
from scripts.flowtest.persona_agent import PersonaAgent  # noqa: E402


def build_pipeline() -> MessagePipeline:
    """Initialize all 3 layers — same pattern as scripts/autotest.py."""
    import anthropic

    from app.engines.context_engine import ContextEngine
    from app.engines.llm_router import LLMRouter

    campaign = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign.reload()
    faq = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign)

    llm_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    llm_router = LLMRouter(settings.LLM_CONFIG_PATH, client=llm_client)

    ctx_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
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


def make_db_factory():
    db_url = settings.TEST_DATABASE_URL or settings.DATABASE_URL
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Flowtest — testes de conversa multi-turno com personas IA "
            "(usa Claude Haiku). Sempre roda com pipeline real (3 camadas)."
        ),
    )
    p.add_argument(
        "--rounds", type=int, default=25,
        help="Total de interações a executar (default: 25).",
    )
    p.add_argument(
        "--persona", type=str, default=None,
        help="Filtra para uma persona específica (ex.: jessica).",
    )
    p.add_argument(
        "--flow", type=str, default=None,
        help="Filtra para um fluxo específico (ex.: compra).",
    )
    p.add_argument(
        "--export", action="store_true",
        help="Gera relatório HTML+JSON em docs/evaluation/reports/.",
    )
    p.add_argument(
        "--seed", type=int, default=None,
        help="Seed do RNG para distribuição reproduzível.",
    )
    return p.parse_args()


def _short_persona(name: str) -> str:
    return name.replace("_", " ").title()


def _short_flow(name: str) -> str:
    return name.replace("_", " ").title()


def print_progress(idx: int, total: int, persona: str, flow: str) -> str:
    label = f"[{idx:02d}/{total:02d}] {_short_persona(persona)} × {_short_flow(flow)}"
    dots = "." * max(0, 45 - len(label))
    line = f"{label} {dots} "
    print(line, end="", flush=True)
    return line


def print_summary(results, total_rounds: int) -> None:
    completed = sum(1 for r in results if r.completed)
    pct = (completed / len(results) * 100) if results else 0.0
    total_turns = sum(r.total_turns for r in results)
    avg_turns = (total_turns / len(results)) if results else 0.0
    total_lat = sum(r.total_latency_ms for r in results)
    avg_lat_turn = (total_lat / total_turns) if total_turns else 0.0

    print()
    print("=" * 64)
    print("RESULTADO")
    print("=" * 64)
    print(
        f"  Interações completas:  {completed}/{len(results)} ({pct:.1f}%)"
    )
    print(f"  Turnos totais:         {total_turns}")
    print(f"  Turnos médios:         {avg_turns:.1f}")
    print(f"  Latência média/turno:  {avg_lat_turn / 1000.0:.1f}s")
    print()
    print("  Por persona:")

    by_persona = {}
    for r in results:
        by_persona.setdefault(r.persona, []).append(r)
    for persona, items in sorted(by_persona.items()):
        n = len(items)
        comp = sum(1 for i in items if i.completed)
        avg_t = sum(i.total_turns for i in items) / n if n else 0.0
        mark = "✅" if comp == n else "⚠️"
        print(
            f"    {persona:<16} {n} interações  {avg_t:.1f} turnos  "
            f"{mark} {comp}/{n}"
        )


async def amain() -> int:
    args = parse_args()

    if not settings.ANTHROPIC_API_KEY:
        print(
            "ERROR: ANTHROPIC_API_KEY is required for flowtest "
            "(no --mock-llm mode)",
            file=sys.stderr,
        )
        return 2

    if not (settings.TEST_DATABASE_URL or settings.DATABASE_URL):
        print(
            "ERROR: configure TEST_DATABASE_URL ou DATABASE_URL em .env",
            file=sys.stderr,
        )
        return 2

    personas = load_personas(filter_persona=args.persona)
    if not personas:
        print(f"ERROR: persona '{args.persona}' não encontrada.", file=sys.stderr)
        return 2

    flows = load_flows(filter_flow=args.flow)
    if not flows:
        print(f"ERROR: fluxo '{args.flow}' não encontrado.", file=sys.stderr)
        return 2

    assignments = distribute_rounds(
        list(personas.keys()), flows, args.rounds, seed=args.seed
    )

    pipeline = build_pipeline()
    session_factory = make_db_factory()
    persona_agent = PersonaAgent(api_key=settings.ANTHROPIC_API_KEY)

    today = __import__("datetime").date.today().isoformat()
    seed_label = args.seed if args.seed is not None else "—"
    print("=" * 64)
    print("FLOWTEST — Teste de Fluxo com Personas IA")
    print(
        f"Data: {today} | Rounds: {len(assignments)} | Seed: {seed_label}"
    )
    print("Delay entre turnos: 7.0s | Retry: 3 tentativas")
    print("=" * 64)
    print()

    flow_lookup = {f["name"]: f for f in flows}
    results = []

    for i, assignment in enumerate(assignments, start=1):
        persona_name = assignment["persona"]
        flow_name = assignment["flow"]
        max_turns = assignment["max_turns"]
        flow_doc = flow_lookup[flow_name]["content"]
        persona_doc = personas[persona_name]
        interaction_id = uuid4().hex[:10]

        prefix_len = len(print_progress(
            i, len(assignments), persona_name, flow_name
        ))

        db = session_factory()
        try:
            result = await run_single_interaction(
                pipeline=pipeline,
                persona_agent=persona_agent,
                persona_name=persona_name,
                persona_doc=persona_doc,
                flow_name=flow_name,
                flow_doc=flow_doc,
                max_turns=max_turns,
                db=db,
                interaction_id=interaction_id,
            )
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            print(f"❌ ERRO: {type(exc).__name__}: {exc}")
            continue
        finally:
            db.close()

        icon = "✅" if result.completed else "⚠️"
        print(
            f"{icon} {result.total_turns} turnos  "
            f"{result.total_latency_ms / 1000.0:.1f}s"
        )
        # silence unused-variable warning
        del prefix_len

        results.append(result)

    print_summary(results, args.rounds)

    # Distribution sanity check (informational)
    flow_counts = Counter(a["flow"] for a in assignments)
    if flow_counts:
        del flow_counts  # already shown via summary tables in HTML

    if args.export:
        html_path, json_path = generate_report(
            results, flows, seed=args.seed
        )
        print()
        print(f"  Relatório: {html_path}")
        print(f"  JSON:      {json_path}")

    print("=" * 64)
    return 0


def main() -> None:
    sys.exit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
