"""MessagePipeline — orquestrador canal-agnóstico (LLM-first).

CRÍTICO: este módulo NÃO pode importar nada de `app.adapters.whatsapp_cloud`.
O contrato é expresso pelo Channel Adapter Pattern (§2.4 do spec) e verificado
por teste estrutural (tests/test_pipeline.py::test_adapter_not_imported).

A partir do Sprint 12 o pipeline é LLM-first: toda mensagem (exceto /start)
passa pelo HaikuEngine. O regex/StateMachine/LLMRouter/ContextEngine são
mantidos APENAS como fallback offline. Ver ADR-002 (LLM-first Pipeline).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.engines.campaign_engine import CampaignEngine
from app.engines.rag_engine import is_product_question
from app.engines.regex_engine import FAQEngine, FAQResponse
from app.engines.state_machine import HandleResult, handle
from app.models.lead import Lead
from app.models.session import Session as SessionModel
from app.schemas.messaging import InboundMessage, OutboundMessage
from app.services import (
    catalog_service,
    lead_service,
    message_service,
    session_service,
)

if TYPE_CHECKING:
    from app.engines.context_engine import ContextEngine
    from app.engines.haiku_engine import HaikuEngine
    from app.engines.llm_router import LLMRouter
    from app.engines.response_validator import ResponseValidator


logger = logging.getLogger(__name__)


MAX_HISTORY_MESSAGES = 20

START_WELCOME_MESSAGE = (
    "👋 Olá! Sou o assistente virtual da *Camisart Belém* — "
    "sua loja de uniformes!\n\n"
    "Faço orçamentos, respondo sobre preços, prazos e bordados. "
    "Para começar, qual é o seu nome? 😊"
)

# Campos do funil que devem ser preservados em session_data
FUNNEL_FIELDS = {
    "nome",
    "segmento",
    "produto",
    "quantidade",
    "personalizacao",
    "prazo",
    "observacoes",
}

# Chaves de sessão que NÃO devem ser limpas no /start (rate limit, etc.)
PRESERVED_SESSION_KEYS = {"rl_window_start", "rl_count"}


class MessagePipeline:
    """Recebe InboundMessage → orquestra engines+services → OutboundMessage."""

    def __init__(
        self,
        faq_engine: FAQEngine,
        campaign_engine: CampaignEngine | None = None,
        haiku_engine: "HaikuEngine | None" = None,
        validator: "ResponseValidator | None" = None,
        llm_router: "LLMRouter | None" = None,
        llm_config: dict | None = None,
        context_engine: "ContextEngine | None" = None,
    ) -> None:
        self._faq_engine = faq_engine
        self._campaign_engine = campaign_engine
        self._haiku_engine = haiku_engine
        self._validator = validator
        self._llm_router = llm_router
        self._llm_config = llm_config or {}
        self._context_engine = context_engine

    # ── Helpers (regex fallback, kept from previous pipeline) ────────────────

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

    # ── Helpers (Haiku path) ──────────────────────────────────────────────────

    def _load_conversation_history(self, session: SessionModel) -> list[dict]:
        """Retorna até MAX_HISTORY_MESSAGES mensagens prévias do session_data."""
        data = session.session_data or {}
        history = data.get("history") or []
        if not isinstance(history, list):
            return []
        return list(history[-MAX_HISTORY_MESSAGES:])

    def _save_to_history(
        self,
        session: SessionModel,
        user_msg: str,
        bot_msg: str,
    ) -> None:
        """Anexa um par user/assistant ao histórico, FIFO até MAX_HISTORY_MESSAGES."""
        data = dict(session.session_data or {})
        history = list(data.get("history") or [])
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": bot_msg})
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]
        data["history"] = history
        session.session_data = data
        flag_modified(session, "session_data")

    def _update_session_data(
        self,
        session: SessionModel,
        dados_extraidos: dict,
    ) -> None:
        """Atualiza campos do funil em session_data (apenas valores não-nulos)."""
        if not dados_extraidos:
            return
        data = dict(session.session_data or {})
        for campo in FUNNEL_FIELDS:
            valor = dados_extraidos.get(campo)
            if valor is None or valor == "":
                continue
            data[campo] = valor
        session.session_data = data
        flag_modified(session, "session_data")
        # Mirror nome_cliente at the column level for analytics & resets
        nome = dados_extraidos.get("nome")
        if nome and not session.nome_cliente:
            session.nome_cliente = str(nome)[:120]

    # ── /start handler ────────────────────────────────────────────────────────

    def _handle_start_command(
        self,
        inbound: InboundMessage,
        session: SessionModel,
        db: Session,
        state_before: str | None,
    ) -> OutboundMessage:
        """Reseta o funil e responde com a mensagem de boas-vindas.

        Mantém apenas chaves de rate limit em session_data. NÃO chama Haiku.
        """
        data = dict(session.session_data or {})
        preserved = {
            k: v for k, v in data.items() if k in PRESERVED_SESSION_KEYS
        }
        session.session_data = preserved
        session.nome_cliente = None
        flag_modified(session, "session_data")

        # Mantém compatibilidade com os testes/fluxo regex: /start → aguarda_nome.
        # O Haiku lê session_data para identidade do cliente, então o nome do
        # estado é irrelevante para o caminho LLM-first.
        next_state = "aguarda_nome"

        message_service.record_inbound(
            db,
            session,
            inbound,
            matched_intent_id="start_command",
            state_before=state_before,
            state_after=next_state,
        )
        session_service.update_state(db, session, next_state)

        message_service.record_outbound(
            db,
            session,
            content=START_WELCOME_MESSAGE,
            state_before=state_before,
            state_after=next_state,
            raw_payload={"type": "text", "body": START_WELCOME_MESSAGE},
        )

        return OutboundMessage(
            channel_id=inbound.channel_id,
            channel_user_id=inbound.channel_user_id,
            response={"type": "text", "body": START_WELCOME_MESSAGE},
            matched_intent_id="start_command",
        )

    # ── Haiku path ────────────────────────────────────────────────────────────

    async def _process_with_haiku(
        self,
        inbound: InboundMessage,
        session: SessionModel,
        db: Session,
        state_before: str | None,
    ) -> OutboundMessage:
        """Caminho principal: HaikuEngine processa a mensagem."""
        assert self._haiku_engine is not None  # checked by caller

        history = self._load_conversation_history(session)
        haiku_resp = await self._haiku_engine.process(
            message=inbound.content,
            conversation_history=history,
            session_data=session.session_data or {},
        )

        if self._validator is not None:
            validation = self._validator.validate(
                resposta=haiku_resp.resposta,
                acao=haiku_resp.acao,
                dados_extraidos=haiku_resp.dados_extraidos,
            )
            if not validation.valid:
                logger.warning("Guardrail issues: %s", validation.issues)

        # Atualiza dados extraídos antes do histórico (caso erro depois)
        self._update_session_data(session, haiku_resp.dados_extraidos)
        self._save_to_history(session, inbound.content, haiku_resp.resposta)

        # Decide próximo estado a partir da ação retornada
        if haiku_resp.acao == "transferir_humano":
            next_state = "aguarda_retorno_humano"
        elif haiku_resp.acao == "lead_completo":
            next_state = "lead_capturado"
        else:
            next_state = session.current_state or "menu"

        message_service.record_inbound(
            db,
            session,
            inbound,
            matched_intent_id=haiku_resp.intent,
            state_before=state_before,
            state_after=next_state,
        )

        session_service.update_state(db, session, next_state)

        # Captura de lead quando o Haiku indicar
        if haiku_resp.acao == "lead_completo":
            # Guard: só captura se não existe lead 'novo' nesta sessão
            existing_lead = (
                db.query(Lead)
                .filter_by(session_id=session.id, status="novo")
                .first()
            )
            if existing_lead is None:
                data = session.session_data or {}
                lead_service.capture(
                    db,
                    session=session,
                    nome_cliente=str(data.get("nome") or session.nome_cliente or "cliente"),
                    telefone=inbound.channel_user_id,
                    segmento=data.get("segmento"),
                    produto=data.get("produto"),
                    quantidade=(
                        int(data["quantidade"])
                        if str(data.get("quantidade", "")).isdigit()
                        else None
                    ),
                    personalizacao=data.get("personalizacao"),
                    prazo_desejado=data.get("prazo"),
                    observacao=data.get("observacoes"),
                )
            else:
                logger.info(
                    "Lead já existe para sessão %s — ignorando duplicata",
                    session.id,
                )

        message_service.record_outbound(
            db,
            session,
            content=haiku_resp.resposta,
            state_before=state_before,
            state_after=next_state,
            raw_payload={"type": "text", "body": haiku_resp.resposta},
        )

        logger.info(
            "Haiku [%s]: %d→%d tokens | acao=%s",
            haiku_resp.intent,
            haiku_resp.tokens_input,
            haiku_resp.tokens_output,
            haiku_resp.acao,
        )

        db.add(session)
        db.commit()

        return OutboundMessage(
            channel_id=inbound.channel_id,
            channel_user_id=inbound.channel_user_id,
            response={"type": "text", "body": haiku_resp.resposta},
            matched_intent_id=haiku_resp.intent,
        )

    # ── Regex fallback (legacy three-layer pipeline) ──────────────────────────

    async def _process_regex_fallback(
        self,
        inbound: InboundMessage,
        session: SessionModel,
        db: Session,
        state_before: str | None,
    ) -> OutboundMessage:
        """Fallback: pipeline regex+LLMRouter+ContextEngine pré-Sprint 12."""
        # ── Camada 1: FAQEngine ─────────────────────────────────────────────
        faq_match = self._faq_engine.match(inbound.content)

        llm_applicable_state = session.current_state in (None, "inicio", "menu")
        result_from_layer2_was_confident = False
        context_already_tried = False
        result: HandleResult | None = None

        # ── Camada 3 prioritária para perguntas técnicas [fix-C1] ───────────
        is_tech_question = (
            self._context_engine is not None
            and llm_applicable_state
            and faq_match is None
            and is_product_question(inbound.content)
        )
        if is_tech_question and self._context_engine is not None:
            ctx_result = await self._context_engine.answer(
                question=inbound.content,
                session_context={
                    "nome_cliente": session.nome_cliente,
                    "current_state": session.current_state,
                },
            )
            context_already_tried = True
            if ctx_result.answer:
                logger.info(
                    "ContextEngine Camada 3 (prioritário): '%s'",
                    inbound.content[:60],
                )
                result = HandleResult(
                    response=FAQResponse(
                        type="text", body=ctx_result.answer
                    ),
                    next_state=session.current_state or "menu",
                    matched_intent_id="context_response",
                )
                result_from_layer2_was_confident = True

        if result is not None:
            pass
        elif (
            faq_match is not None
            or not self._llm_router
            or not llm_applicable_state
        ):
            if faq_match is not None:
                result_from_layer2_was_confident = True
            result = handle(
                message=inbound.content,
                session=session,
                faq_engine=self._faq_engine,
                campaign_engine=self._campaign_engine,
            )
        else:
            # ── Camada 2: LLMRouter ─────────────────────────────────────────
            context = self._build_llm_context(session, db)
            known_intents = self._faq_engine.intent_ids()
            classification = await self._llm_router.classify_intent(
                message=inbound.content,
                session_context=context,
                known_intents=known_intents,
            )
            thresholds = self._llm_router.thresholds
            medium = thresholds.get("medium", 0.60)
            low = thresholds.get("low", 0.40)

            synthesized: HandleResult | None = None
            if (
                classification.intent_id
                and classification.confidence >= medium
            ):
                logger.info(
                    "LLM Camada 2: '%s' → %s (%.2f)",
                    inbound.content[:50],
                    classification.intent_id,
                    classification.confidence,
                )
                synthesized = self._result_from_intent(
                    classification.intent_id, session
                )
                if synthesized is not None:
                    result_from_layer2_was_confident = True
            elif (
                classification.intent_id
                and classification.confidence >= low
            ):
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
                result = handle(
                    message=inbound.content,
                    session=session,
                    faq_engine=self._faq_engine,
                    campaign_engine=self._campaign_engine,
                )

        # ── Camada 3: ContextEngine ─────────────────────────────────────────
        if (
            self._context_engine
            and not context_already_tried
            and llm_applicable_state
            and is_product_question(inbound.content)
            and not result_from_layer2_was_confident
        ):
            ctx_result = await self._context_engine.answer(
                question=inbound.content,
                session_context={
                    "nome_cliente": session.nome_cliente,
                    "current_state": session.current_state,
                },
            )
            if ctx_result.answer:
                logger.info(
                    "ContextEngine Camada 3: '%s' → resposta gerada (%d tokens contexto)",
                    inbound.content[:50],
                    ctx_result.tokens_used,
                )
                result = HandleResult(
                    response=FAQResponse(type="text", body=ctx_result.answer),
                    next_state=session.current_state or "menu",
                    matched_intent_id="context_response",
                )

        flag_modified(session, "session_data")

        message_service.record_inbound(
            db,
            session,
            inbound,
            matched_intent_id=result.matched_intent_id,
            state_before=state_before,
            state_after=result.next_state,
        )

        session_service.update_state(db, session, result.next_state)

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
            for key in list(data.keys()):
                if key.startswith("orcamento_"):
                    data.pop(key, None)
            session.session_data = data

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
            matched_intent_id=result.matched_intent_id,
        )

    # ── Entry point ───────────────────────────────────────────────────────────

    async def process(
        self, inbound: InboundMessage, db: Session
    ) -> OutboundMessage | None:
        """Processa mensagem de entrada, persiste e devolve resposta canônica.

        Retorna None se a mensagem foi rejeitada (rate limit ou duplicada).
        """
        # Idempotência
        if message_service.already_processed(
            db, inbound.channel_id, inbound.channel_message_id
        ):
            logger.info(
                "Mensagem já processada, ignorando: %s",
                inbound.channel_message_id,
            )
            return None

        session, _was_reset = session_service.get_or_create_session(
            db,
            channel_id=inbound.channel_id,
            channel_user_id=inbound.channel_user_id,
            display_name=inbound.display_name,
        )

        if not session_service.check_rate_limit(session, db):
            logger.warning(
                "Rate limit excedido para %s/%s",
                inbound.channel_id,
                inbound.channel_user_id,
            )
            return None

        state_before = session.current_state

        # /start: reset direto, sem Haiku
        content = (inbound.content or "").strip()
        if content == "/start":
            return self._handle_start_command(
                inbound, session, db, state_before
            )

        # Caminho principal: HaikuEngine
        if self._haiku_engine is not None:
            try:
                return await self._process_with_haiku(
                    inbound, session, db, state_before
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "HaikuEngine erro: %s — fallback para regex",
                    exc,
                )
                db.rollback()

        # Fallback: pipeline regex (Sprints 1-11)
        return await self._process_regex_fallback(
            inbound, session, db, state_before
        )
