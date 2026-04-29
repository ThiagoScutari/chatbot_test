"""FAQEngine — regex determinístico puro (sem I/O, sem side effects).

Recebe texto do usuário e retorna `FAQMatch | None`.
Integra com `CampaignEngine` opcionalmente para aplicar intents e overrides
de campanhas sazonais ativas.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.engines.campaign_engine import CampaignEngine


logger = logging.getLogger(__name__)


# ── Schemas ──────────────────────────────────────────────────────────────────


class ResponseButton(BaseModel):
    id: str
    title: str


class ResponseListItem(BaseModel):
    id: str
    title: str
    description: str | None = None


class FAQResponse(BaseModel):
    type: Literal["text", "buttons", "list"]
    body: str
    buttons: list[ResponseButton] | None = None
    list_items: list[ResponseListItem] | None = None
    list_button_label: str | None = None
    footer: str | None = None


class FAQIntent(BaseModel):
    id: str
    priority: int = 0
    patterns: list[str]
    response: FAQResponse
    follow_up_state: Literal[
        "menu",
        "aguarda_pedido",
        "aguarda_orcamento",
        "aguarda_nome",
        "encaminhar_humano",
        "aguarda_retorno_humano",
        "coleta_orcamento_segmento",
        "lead_capturado",
        "conversa_finalizada",
    ] | None = None


class FAQFallback(BaseModel):
    response: FAQResponse


class FAQFile(BaseModel):
    version: str
    intents: list[FAQIntent] = Field(default_factory=list)
    fallback: FAQFallback


class FAQMatch(BaseModel):
    intent_id: str
    response: FAQResponse
    follow_up_state: str | None = None


# ── Engine ───────────────────────────────────────────────────────────────────


class FAQEngine:
    """Match de regex contra intents declarados em faq.json.

    Pure function: sem I/O dinâmico após o load inicial, sem side effects.
    """

    def __init__(
        self,
        faq_path: Path,
        campaign_engine: "CampaignEngine | None" = None,
    ) -> None:
        self._faq_path = Path(faq_path)
        self._campaign_engine = campaign_engine
        self._base_intents: list[FAQIntent] = []
        self._fallback: FAQResponse = FAQResponse(
            type="text", body="Não entendi."
        )
        self._load()

    def _load(self) -> None:
        raw = json.loads(self._faq_path.read_text(encoding="utf-8"))
        parsed = FAQFile(**raw)
        # Ordena por priority desc para curto-circuitar o match
        self._base_intents = sorted(
            parsed.intents, key=lambda i: i.priority, reverse=True
        )
        self._fallback = parsed.fallback.response

    @staticmethod
    def _normalize(text: str) -> str:
        """Lower + strip + remove diacríticos (NFD decomposition)."""
        text = text.lower().strip()
        nfd = unicodedata.normalize("NFD", text)
        # Remove combining marks (acentos)
        return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")

    def _current_intents(self) -> list[FAQIntent]:
        """Merge de intents de campanha ativa + base."""
        if self._campaign_engine is not None:
            return self._campaign_engine.merged_intents(self._base_intents)
        return self._base_intents

    def match(self, message: str) -> FAQMatch | None:
        """Tenta casar `message` contra os intents. Retorna FAQMatch ou None."""
        normalized = self._normalize(message)

        for intent in self._current_intents():
            for pattern in intent.patterns:
                try:
                    # Normaliza o próprio pattern para casar sem acentos
                    norm_pattern = self._normalize_pattern(pattern)
                    if re.search(norm_pattern, normalized, flags=re.IGNORECASE):
                        response = intent.response
                        if self._campaign_engine is not None:
                            response = self._campaign_engine.apply_override(
                                intent.id, response
                            )
                        return FAQMatch(
                            intent_id=intent.id,
                            response=response,
                            follow_up_state=intent.follow_up_state,
                        )
                except re.error as exc:
                    logger.warning(
                        "Pattern inválido em intent '%s': %s (%s)",
                        intent.id,
                        pattern,
                        exc,
                    )
        return None

    @staticmethod
    def _normalize_pattern(pattern: str) -> str:
        """Remove acentos do pattern para casar com texto normalizado.

        Classes como `[çc]` e `[áa]` permanecem válidas; apenas normalizamos
        letras acentuadas literais fora de classes. Estratégia simples:
        aplicar NFD no pattern inteiro e remover combining marks.
        """
        nfd = unicodedata.normalize("NFD", pattern)
        return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")

    def fallback_response(self) -> FAQResponse:
        """Retorna o FAQResponse de fallback configurado."""
        return self._fallback

    def intent_ids(self) -> list[str]:
        """Retorna lista de todos os intent_ids carregados."""
        return [intent.id for intent in self._base_intents]

    def match_by_id(self, intent_id: str) -> FAQMatch | None:
        """Retorna FAQMatch para um intent_id conhecido — usado pela Camada 2.

        Quando o LLMRouter classifica uma mensagem, precisamos do template
        de resposta correspondente sem re-executar regex matching.
        """
        for intent in self._current_intents():
            if intent.id == intent_id:
                response = intent.response
                if self._campaign_engine is not None:
                    response = self._campaign_engine.apply_override(
                        intent.id, response
                    )
                return FAQMatch(
                    intent_id=intent.id,
                    response=response,
                    follow_up_state=intent.follow_up_state,
                )
        return None
