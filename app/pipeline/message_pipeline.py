"""MessagePipeline — orquestrador canal-agnóstico.

CRÍTICO: este módulo NÃO pode importar nada de `app.adapters.whatsapp_cloud`.
O contrato é expresso pelo Channel Adapter Pattern (§2.4 do spec) e verificado
por teste estrutural (tests/test_pipeline.py::test_adapter_not_imported).
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.engines.campaign_engine import CampaignEngine
from app.engines.regex_engine import FAQEngine
from app.engines.state_machine import HandleResult, handle
from app.schemas.messaging import InboundMessage, OutboundMessage
from app.services import lead_service, message_service, session_service


logger = logging.getLogger(__name__)


class MessagePipeline:
    """Recebe InboundMessage → orquestra engines+services → OutboundMessage."""

    def __init__(
        self,
        faq_engine: FAQEngine,
        campaign_engine: CampaignEngine | None = None,
    ) -> None:
        self._faq_engine = faq_engine
        self._campaign_engine = campaign_engine

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

        # Executa máquina de estados
        state_before = session.current_state
        result: HandleResult = handle(
            message=inbound.content,
            session=session,
            faq_engine=self._faq_engine,
            campaign_engine=self._campaign_engine,
        )

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
