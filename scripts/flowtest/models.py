"""Dataclasses for flowtest results and pipeline responses."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Turn:
    number: int
    client_message: str
    bot_response: str
    intent: str | None
    latency_ms: int


@dataclass
class FlowTestResult:
    interaction_id: str
    persona: str
    flow: str
    turns: list[Turn]
    total_turns: int
    completed: bool              # agent sent __END__
    total_latency_ms: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PipelineResponse:
    text: str
    intent_id: str | None
    latency_ms: int
