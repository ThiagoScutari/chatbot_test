"""FlowTest Runner — orchestrates persona-driven conversation testing.

Loads persona/flow docs, distributes rounds, and runs each interaction
as a multi-turn conversation against the real MessagePipeline.

Pipeline initialization mirrors scripts/autotest.py — all 3 layers active.
The flowtest never runs in mock mode; it always uses the real Claude API.
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import FlowTestResult, PipelineResponse, Turn
from .persona_agent import PersonaAgent


PERSONAS_DIR = Path(__file__).parent / "personas"
FLOWS_DIR = Path(__file__).parent / "flows"


def load_personas(filter_persona: str | None = None) -> dict[str, str]:
    """Load persona .md files. Returns ``{name: content}``."""
    personas: dict[str, str] = {}
    for f in sorted(PERSONAS_DIR.glob("*.md")):
        name = f.stem
        if filter_persona and name != filter_persona:
            continue
        personas[name] = f.read_text(encoding="utf-8")
    return personas


def load_flows(filter_flow: str | None = None) -> list[dict[str, Any]]:
    """Load flow .md files. Returns ``[{name, weight, content, max_turns}]``."""
    flows: list[dict[str, Any]] = []
    for f in sorted(FLOWS_DIR.glob("*.md")):
        name = f.stem
        if filter_flow and name != filter_flow:
            continue
        content = f.read_text(encoding="utf-8")
        weight_match = re.search(r"## Peso\s*\n\s*(\d+)", content)
        weight = int(weight_match.group(1)) if weight_match else 10
        turns_match = re.search(r"## Máximo de turnos\s*\n\s*(\d+)", content)
        max_turns = int(turns_match.group(1)) if turns_match else 10
        flows.append({
            "name": name,
            "weight": weight,
            "content": content,
            "max_turns": max_turns,
        })
    return flows


def distribute_rounds(
    persona_names: list[str],
    flows: list[dict[str, Any]],
    total_rounds: int,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Distribute rounds equally among personas, weighted among flows.

    Returns a shuffled list of ``{"persona", "flow", "max_turns"}`` dicts.
    """
    rng = random.Random(seed)

    rounds_per_persona = total_rounds // len(persona_names)
    remainder = total_rounds % len(persona_names)

    flow_names = [f["name"] for f in flows]
    flow_weights = [f["weight"] for f in flows]
    flow_max_turns = {f["name"]: f["max_turns"] for f in flows}

    assignments: list[dict[str, Any]] = []
    for i, persona in enumerate(persona_names):
        n = rounds_per_persona + (1 if i < remainder else 0)
        for _ in range(n):
            chosen = rng.choices(flow_names, weights=flow_weights, k=1)[0]
            assignments.append({
                "persona": persona,
                "flow": chosen,
                "max_turns": flow_max_turns[chosen],
            })

    rng.shuffle(assignments)
    return assignments


async def send_to_pipeline(
    pipeline,
    text: str,
    channel_user_id: str,
    db,
) -> PipelineResponse:
    """Send a message through the pipeline and measure latency.

    Uses the canonical InboundMessage from app.schemas.messaging — the
    pipeline expects ``content`` (not ``text``) and timestamp/raw_payload.
    """
    from app.schemas.messaging import InboundMessage

    inbound = InboundMessage(
        channel_id="telegram",
        channel_message_id=f"ft_{uuid4().hex[:12]}",
        channel_user_id=channel_user_id,
        display_name=None,
        content=text,
        timestamp=datetime.now(timezone.utc),
        raw_payload={"flowtest": True, "text": text},
    )

    start = time.perf_counter()
    try:
        outbound = await pipeline.process(inbound, db)
    except Exception:
        db.rollback()
        raise
    elapsed = int((time.perf_counter() - start) * 1000)

    response_text = ""
    intent_id: str | None = None
    if outbound is not None:
        response_text = outbound.response.get("body", "") or ""
        intent_id = outbound.matched_intent_id

    return PipelineResponse(
        text=response_text,
        intent_id=intent_id,
        latency_ms=elapsed,
    )


async def run_single_interaction(
    pipeline,
    persona_agent: PersonaAgent,
    persona_name: str,
    persona_doc: str,
    flow_name: str,
    flow_doc: str,
    max_turns: int,
    db,
    interaction_id: str,
) -> FlowTestResult:
    """Run ONE complete multi-turn conversation."""
    channel_user_id = f"flowtest_{interaction_id}"
    turns: list[Turn] = []

    # Turn 0: /start
    bot_resp = await send_to_pipeline(pipeline, "/start", channel_user_id, db)
    turns.append(Turn(
        number=0,
        client_message="/start",
        bot_response=bot_resp.text,
        intent=bot_resp.intent_id,
        latency_ms=bot_resp.latency_ms,
    ))

    conversation_history: list[dict] = [
        {"role": "user", "content": bot_resp.text or "(sem resposta)"}
    ]

    completed = False
    for turn_num in range(1, max_turns):
        # Delay between turns to stay under rate limit (10 msgs/min per user)
        await asyncio.sleep(7.0)

        # Retry up to 3 times on connection / transient errors
        for attempt in range(3):
            try:
                client_msg = await persona_agent.generate_message(
                    persona_doc=persona_doc,
                    flow_doc=flow_doc,
                    conversation_history=conversation_history,
                    turn_number=turn_num,
                    max_turns=max_turns,
                )
                break
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(10)
                    continue
                raise

        if "__END__" in client_msg:
            completed = True
            break

        # Same retry policy for the pipeline call
        for attempt in range(3):
            try:
                bot_resp = await send_to_pipeline(
                    pipeline, client_msg, channel_user_id, db
                )
                break
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(10)
                    continue
                raise

        turns.append(Turn(
            number=turn_num,
            client_message=client_msg,
            bot_response=bot_resp.text,
            intent=bot_resp.intent_id,
            latency_ms=bot_resp.latency_ms,
        ))

        conversation_history.append(
            {"role": "assistant", "content": client_msg}
        )
        conversation_history.append(
            {"role": "user", "content": bot_resp.text or "(sem resposta)"}
        )

    return FlowTestResult(
        interaction_id=interaction_id,
        persona=persona_name,
        flow=flow_name,
        turns=turns,
        total_turns=len(turns),
        completed=completed,
        total_latency_ms=sum(t.latency_ms for t in turns),
    )
