"""CampaignEngine — campanhas sazonais configuráveis sem deploy.

Lê `campaigns.json`, expõe campanhas ativas, merged intents e overrides.
Integra com FAQEngine via `merged_intents()` e `apply_override()`.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.engines.regex_engine import FAQIntent, FAQResponse


logger = logging.getLogger(__name__)


# ── Models ───────────────────────────────────────────────────────────────────


class Campaign(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool
    active_from: date
    active_until: date
    lead_segmento_default: str | None = None
    greeting_override: str | None = None
    intents: list[FAQIntent] = Field(default_factory=list)
    response_overrides: dict[str, FAQResponse] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self) -> "Campaign":
        if self.active_from > self.active_until:
            raise ValueError(
                f"Campanha '{self.id}': active_from ({self.active_from}) deve "
                f"ser anterior ou igual a active_until ({self.active_until})"
            )
        return self

    @model_validator(mode="after")
    def warn_low_priority_intents(self) -> "Campaign":
        for intent in self.intents:
            if intent.priority < 50:
                logger.warning(
                    "Campanha '%s': intent '%s' tem priority=%d. "
                    "Recomendado >= 50 para sobrepor FAQ base.",
                    self.id,
                    intent.id,
                    intent.priority,
                )
        return self


class CampaignsFile(BaseModel):
    version: str
    campaigns: list[Campaign] = Field(default_factory=list)


# ── Engine ───────────────────────────────────────────────────────────────────


class CampaignEngine:
    """Gerencia campanhas sazonais configuradas em campaigns.json."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._campaigns: list[Campaign] = []

    def reload(self) -> int:
        """Relê o arquivo. Retorna total de campanhas carregadas."""
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        cleaned = self._strip_comments(raw)
        data = CampaignsFile(**cleaned)
        self._campaigns = data.campaigns
        logger.info(
            "CampaignEngine: %d campanhas carregadas (%d ativas hoje).",
            len(self._campaigns),
            len(self.active_campaigns()),
        )
        return len(self._campaigns)

    def active_campaigns(self, at: date | None = None) -> list[Campaign]:
        today = at or date.today()
        return [
            c
            for c in self._campaigns
            if c.enabled and c.active_from <= today <= c.active_until
        ]

    def merged_intents(self, base_intents: list[FAQIntent]) -> list[FAQIntent]:
        """Intents de campanhas ativas (priority>=50) + intents base."""
        campaign_intents: list[FAQIntent] = []
        for campaign in self.active_campaigns():
            campaign_intents.extend(campaign.intents)
        ordered = sorted(
            campaign_intents, key=lambda i: i.priority, reverse=True
        )
        ordered += base_intents
        return ordered

    def apply_override(self, intent_id: str, base: FAQResponse) -> FAQResponse:
        """Retorna override de campanha ativa se existir; caso contrário, base."""
        for campaign in self.active_campaigns():
            if intent_id in campaign.response_overrides:
                return campaign.response_overrides[intent_id]
        return base

    def active_greeting(self) -> str | None:
        for campaign in self.active_campaigns():
            if campaign.greeting_override:
                return campaign.greeting_override
        return None

    def default_segmento(self) -> str | None:
        for campaign in self.active_campaigns():
            if campaign.lead_segmento_default:
                return campaign.lead_segmento_default
        return None

    def status(self) -> dict[str, Any]:
        today = date.today()
        return {
            "today": today.isoformat(),
            "total_loaded": len(self._campaigns),
            "active": [
                {
                    "id": c.id,
                    "name": c.name,
                    "active_until": c.active_until.isoformat(),
                    "days_remaining": (c.active_until - today).days,
                    "intents_count": len(c.intents),
                    "has_overrides": bool(c.response_overrides),
                    "has_greeting": bool(c.greeting_override),
                }
                for c in self.active_campaigns()
            ],
            "upcoming": [
                {
                    "id": c.id,
                    "name": c.name,
                    "active_from": c.active_from.isoformat(),
                    "days_until": (c.active_from - today).days,
                }
                for c in self._campaigns
                if c.enabled and c.active_from > today
            ],
        }

    @staticmethod
    def _strip_comments(obj: Any) -> Any:
        """Remove recursivamente chaves começando com '_' antes de parsear."""
        if isinstance(obj, dict):
            return {
                k: CampaignEngine._strip_comments(v)
                for k, v in obj.items()
                if not k.startswith("_")
            }
        if isinstance(obj, list):
            return [CampaignEngine._strip_comments(item) for item in obj]
        return obj
