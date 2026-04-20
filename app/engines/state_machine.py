"""StateMachine — lógica pura de transição de estados.

Função `handle()`: recebe a mensagem do usuário + sessão + faq_engine
(opcionalmente campaign_engine) e retorna `HandleResult` com a resposta,
o próximo estado e uma ação opcional (send_catalog, capture_lead,
forward_to_human).

Esta camada NÃO faz I/O — toda persistência é responsabilidade dos
services. NÃO conhece canal externo (InboundMessage é apenas texto).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app.engines.campaign_engine import CampaignEngine
from app.engines.regex_engine import FAQEngine, FAQResponse
from app.models.session import Session as SessionModel


# Estados
INICIO = "inicio"
AGUARDA_NOME = "aguarda_nome"
MENU = "menu"
AGUARDA_PEDIDO = "aguarda_pedido"
ENVIA_CATALOGO = "envia_catalogo"
COLETA_ORCAMENTO_SEGMENTO = "coleta_orcamento_segmento"
ENCAMINHAR_HUMANO = "encaminhar_humano"
FIM = "fim"


class HandleResult(BaseModel):
    response: FAQResponse
    next_state: str
    matched_intent_id: str | None = None
    action: Literal["send_catalog", "capture_lead", "forward_to_human"] | None = (
        None
    )
    action_payload: dict[str, Any] | None = None


def _text(body: str) -> FAQResponse:
    return FAQResponse(type="text", body=body)


def _menu_buttons() -> FAQResponse:
    return FAQResponse(
        type="buttons",
        body="Como posso te ajudar?",
        buttons=[  # type: ignore[arg-type]
            {"id": "consultar_pedido", "title": "📦 Meu pedido"},
            {"id": "ver_catalogo", "title": "👕 Ver catálogo"},
            {"id": "falar_humano", "title": "🧑 Falar atendente"},
        ],
    )


def _greeting(
    session: SessionModel, campaign_engine: CampaignEngine | None
) -> str:
    if campaign_engine is not None:
        override = campaign_engine.active_greeting()
        if override:
            return override
    nome = session.nome_cliente
    if nome:
        return f"Olá de novo, {nome}! 😊 Como posso ajudar hoje?"
    return "Olá! Seja bem-vindo(a) à Camisart. Com quem tenho o prazer? 😊"


def handle(
    message: str,
    session: SessionModel,
    faq_engine: FAQEngine,
    campaign_engine: CampaignEngine | None = None,
) -> HandleResult:
    """Processa uma mensagem considerando o estado atual da sessão.

    Regras:
    - Em qualquer estado "aberto" (AGUARDA_NOME, MENU), tenta FAQEngine.match()
      primeiro — se bate um intent de prioridade alta (>=50), responde sem
      alterar o estado (exceto se o intent define `follow_up_state`).
    - Se não bate, segue o fluxo da máquina de estados.
    """
    estado_atual = session.current_state or INICIO
    texto = (message or "").strip()

    # ── Estado INICIO: envia saudação e avança para AGUARDA_NOME ──────────
    if estado_atual == INICIO:
        return HandleResult(
            response=_text(_greeting(session, campaign_engine)),
            next_state=AGUARDA_NOME,
        )

    # ── Tenta FAQEngine em qualquer estado "aberto" ──────────────────────
    faq_match = faq_engine.match(texto) if texto else None

    if estado_atual == AGUARDA_NOME:
        if faq_match is not None and faq_match.follow_up_state:
            # Um intent bem-vindo foi detectado antes do nome — responde,
            # mas ainda pede o nome em seguida.
            return HandleResult(
                response=faq_match.response,
                next_state=AGUARDA_NOME,
                matched_intent_id=faq_match.intent_id,
            )
        if not texto:
            return HandleResult(
                response=_text("Por favor, digite o seu nome."),
                next_state=AGUARDA_NOME,
            )
        session.nome_cliente = texto
        return HandleResult(
            response=FAQResponse(
                type="buttons",
                body=(
                    f"Prazer, *{texto}*! Como posso te ajudar?"
                ),
                buttons=[  # type: ignore[arg-type]
                    {"id": "consultar_pedido", "title": "📦 Meu pedido"},
                    {"id": "ver_catalogo", "title": "👕 Ver catálogo"},
                    {"id": "falar_humano", "title": "🧑 Falar atendente"},
                ],
            ),
            next_state=MENU,
        )

    if estado_atual == MENU:
        # FAQ tem precedência no MENU
        if faq_match is not None:
            next_state = faq_match.follow_up_state or MENU
            return HandleResult(
                response=faq_match.response,
                next_state=next_state,
                matched_intent_id=faq_match.intent_id,
            )

        # Roteamento: aceita tanto o id original do botão (WhatsApp Interactive)
        # quanto o número da posição (1/2/3) para canais que renderizam como
        # lista numerada (Telegram) ou para clientes que digitam livre.
        menu_alias = {
            "1": "consultar_pedido",
            "2": "ver_catalogo",
            "3": "falar_humano",
        }
        acao_id = menu_alias.get(texto, texto)

        if acao_id == "consultar_pedido":
            return HandleResult(
                response=_text(
                    "Informe o número do pedido (ex: 1001):"
                ),
                next_state=AGUARDA_PEDIDO,
            )
        if acao_id == "ver_catalogo":
            return HandleResult(
                response=_text(
                    "Enviando nosso catálogo em PDF 👕"
                ),
                next_state=ENVIA_CATALOGO,
                action="send_catalog",
            )
        if acao_id == "falar_humano":
            return HandleResult(
                response=_text(
                    "Beleza! Vou te transferir para um atendente humano. "
                    "Em instantes alguém entra em contato 🧑"
                ),
                next_state=ENCAMINHAR_HUMANO,
                action="forward_to_human",
            )
        # Fallback no menu
        return HandleResult(
            response=faq_engine.fallback_response(),
            next_state=MENU,
        )

    if estado_atual == AGUARDA_PEDIDO:
        if faq_match is not None:
            return HandleResult(
                response=faq_match.response,
                next_state=AGUARDA_PEDIDO,
                matched_intent_id=faq_match.intent_id,
            )
        if not texto.isdigit():
            return HandleResult(
                response=_text(
                    "Número de pedido inválido. Digite apenas números (ex: 1001)."
                ),
                next_state=AGUARDA_PEDIDO,
            )
        # Na Fase 1 ainda não temos tabela de pedidos integrada — devolve
        # mensagem genérica e volta ao menu.
        return HandleResult(
            response=_text(
                f"Consultando o pedido #{texto}... (em breve integração "
                "com o sistema da Camisart)"
            ),
            next_state=MENU,
        )

    if estado_atual == ENCAMINHAR_HUMANO:
        return HandleResult(
            response=_text(
                "Já encaminhei ao atendente humano. Aguarde um instante 🙏"
            ),
            next_state=ENCAMINHAR_HUMANO,
        )

    if estado_atual == ENVIA_CATALOGO:
        return HandleResult(
            response=_menu_buttons(),
            next_state=MENU,
        )

    # Estado desconhecido — volta ao menu
    return HandleResult(
        response=_menu_buttons(),
        next_state=MENU,
    )
