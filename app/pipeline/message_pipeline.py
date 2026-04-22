"""MessagePipeline — orquestrador canal-agnóstico.

CRÍTICO: este módulo NÃO pode importar nada de `app.adapters.whatsapp_cloud`.
O contrato é expresso pelo Channel Adapter Pattern (§2.4 do spec) e verificado
por teste estrutural (tests/test_pipeline.py::test_adapter_not_imported).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.engines.campaign_engine import CampaignEngine
from app.engines.regex_engine import FAQEngine, FAQResponse
from app.engines.state_machine import HandleResult, handle
from app.models.session import Session as SessionModel
from app.schemas.messaging import InboundMessage, OutboundMessage
from app.services import (
    catalog_service,
    lead_service,
    message_service,
    session_service,
)

if TYPE_CHECKING:
    from app.engines.llm_router import LLMRouter


logger = logging.getLogger(__name__)


class MessagePipeline:
    """Recebe InboundMessage → orquestra engines+services → OutboundMessage."""

    def __init__(
        self,
        faq_engine: FAQEngine,
        campaign_engine: CampaignEngine | None = None,
        llm_router: "LLMRouter | None" = None,
        llm_config: dict | None = None,
    ) -> None:
        self._faq_engine = faq_engine
        self._campaign_engine = campaign_engine
        self._llm_router = llm_router
        self._llm_config = llm_config or {}

    def _build_llm_context(
        self, session: SessionModel, db: Session
    ) -> dict:
        """Builds context dict with last N messages for LLM prompt."""
        from app.models.message import Message

        last_msgs = (
            db.query(Message)
            .filter_by(session_id=session.id, direction="in")
            .order_by(Message.created_at.desc())
            .limit(3)
            .all()
        )
        return {
            "last_messages": [m.content for m in reversed(last_msgs)],
            "current_state": session.current_state,
            "nome_cliente": session.nome_cliente,
        }

    def _result_from_intent(
        self, intent_id: str, session: SessionModel
    ) -> HandleResult | None:
        """Constrói HandleResult a partir de um intent_id classificado pelo LLM."""
        faq_match = self._faq_engine.match_by_id(intent_id)
        if faq_match is None:
            return None
        next_state = faq_match.follow_up_state or session.current_state or "menu"
        return HandleResult(
            response=faq_match.response,
            next_state=next_state,
            matched_intent_id=faq_match.intent_id,
        )

    async def process(
        self, inbound: InboundMessage, db: Session
    ) -> OutboundMessage | None:
        """Processa mensagem de entrada, persiste e devolve resposta canônica.

        Retorna None se a mensagem foi rejeitada (rate limit ou duplicada).
        """
        # Idempotência: mensagem já processada → ignora
        if message_service.already_processed(
            db, inbound.channel_id, inbound.channel_message_id
        ):
            logger.info(
                "Mensagem já processada, ignorando: %s",
                inbound.channel_message_id,
            )
            return None

        # Sessão + timeout reset
        session, _was_reset = session_service.get_or_create_session(
            db,
            channel_id=inbound.channel_id,
            channel_user_id=inbound.channel_user_id,
            display_name=inbound.display_name,
        )

        # Rate limit
        if not session_service.check_rate_limit(session, db):
            logger.warning(
                "Rate limit excedido para %s/%s",
                inbound.channel_id,
                inbound.channel_user_id,
            )
            return None

        state_before = session.current_state

        # ── Camada 1: FAQEngine (regex, sem custo) ───────────────────────────
        faq_match = self._faq_engine.match(inbound.content)

        if faq_match is not None or not self._llm_router:
            # Camada 1 resolveu OU LLMRouter não configurado — fluxo padrão
            result: HandleResult = handle(
                message=inbound.content,
                session=session,
                faq_engine=self._faq_engine,
                campaign_engine=self._campaign_engine,
            )
        else:
            # ── Camada 2: LLMRouter ──────────────────────────────────────────
            context = self._build_llm_context(session, db)
            known_intents = self._faq_engine.intent_ids()
            classification = await self._llm_router.classify_intent(
                message=inbound.content,
                session_context=context,
                known_intents=known_intents,
            )
            thresholds = self._llm_router.thresholds
            high = thresholds.get("high", 0.85)
            medium = thresholds.get("medium", 0.60)
            low = thresholds.get("low", 0.40)

            synthesized: HandleResult | None = None
            if (
                classification.intent_id
                and classification.confidence >= medium
            ):
                # Confiança alta ou média — responde direto com o template
                logger.info(
                    "LLM Camada 2: '%s' → %s (%.2f)",
                    inbound.content[:50],
                    classification.intent_id,
                    classification.confidence,
                )
                synthesized = self._result_from_intent(
                    classification.intent_id, session
                )
            elif (
                classification.intent_id
                and classification.confidence >= low
            ):
                # Confiança baixa — pede confirmação
                label = classification.intent_id.replace("_", " ")
                synthesized = HandleResult(
                    response=FAQResponse(
                        type="buttons",
                        body=(
                            f"Não entendi bem. "
                            f"Você quer saber sobre *{label}*?"
                        ),
                        buttons=[  # type: ignore[arg-type]
                            {"id": classification.intent_id, "title": "✅ Sim"},
                            {"id": "falar_humano", "title": "❌ Outro assunto"},
                        ],
                    ),
                    next_state=session.current_state or "menu",
                )

            if synthesized is not None:
                result = synthesized
            else:
                # Confiança muito baixa, None ou erro — delega para state_machine
                result = handle(
                    message=inbound.content,
                    session=session,
                    faq_engine=self._faq_engine,
                    campaign_engine=self._campaign_engine,
                )

        # state_machine pode mutar session.session_data in-place
        # (ex.: orcamento_quantidade). JSONB não detecta mutação in-place,
        # então marcamos explicitamente como dirty para garantir persistência.
        flag_modified(session, "session_data")

        # Persiste mensagem inbound
        message_service.record_inbound(
            db,
            session,
            inbound,
            matched_intent_id=result.matched_intent_id,
            state_before=state_before,
            state_after=result.next_state,
        )

        # Atualiza estado da sessão
        session_service.update_state(db, session, result.next_state)

        # Ação: enviar catálogo (envio direto via adapter do canal)
        if result.action == "send_catalog":
            catalog_text = catalog_service.build_catalog_message()
            catalog_outbound = OutboundMessage(
                channel_id=inbound.channel_id,
                channel_user_id=inbound.channel_user_id,
                response={"type": "text", "body": catalog_text},
            )
            try:
                from app.adapters.registry import get as get_adapter

                adapter = get_adapter(inbound.channel_id)
                await adapter.send(catalog_outbound)
                message_service.record_outbound(
                    db,
                    session,
                    content=catalog_text,
                    state_before=state_before,
                    state_after=result.next_state,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Erro ao enviar catálogo via %s: %s",
                    inbound.channel_id,
                    exc,
                )

        # Ação: captura de lead (grava Lead + audit_log antes do commit)
        if result.action == "capture_lead":
            data = session.session_data or {}
            lead_service.capture(
                db,
                session=session,
                nome_cliente=session.nome_cliente or "cliente",
                telefone=inbound.channel_user_id,
                segmento=data.get("orcamento_segmento"),
                produto=data.get("orcamento_produto"),
                quantidade=data.get("orcamento_quantidade"),
                personalizacao=data.get("orcamento_personalizacao"),
                prazo_desejado=data.get("orcamento_prazo"),
            )
            # Limpa chaves orcamento_* após captura
            for key in list(data.keys()):
                if key.startswith("orcamento_"):
                    data.pop(key, None)
            session.session_data = data

        # Persiste outbound
        message_service.record_outbound(
            db,
            session,
            content=result.response.body,
            state_before=state_before,
            state_after=result.next_state,
            raw_payload=result.response.model_dump(),
        )

        return OutboundMessage(
            channel_id=inbound.channel_id,
            channel_user_id=inbound.channel_user_id,
            response=result.response.model_dump(),
        )
