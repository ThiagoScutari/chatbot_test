"""StateMachine — lógica pura de transição de estados.

Função `handle()`: recebe a mensagem do usuário + sessão + faq_engine
(opcionalmente campaign_engine) e retorna `HandleResult` com a resposta,
o próximo estado e uma ação opcional (send_catalog, capture_lead,
forward_to_human).

Esta camada NÃO faz I/O — toda persistência é responsabilidade dos
services. NÃO conhece canal externo (InboundMessage é apenas texto).
"""
from __future__ import annotations

import unicodedata
from typing import Any, Literal

from pydantic import BaseModel

from app.engines.campaign_engine import CampaignEngine
from app.engines.regex_engine import FAQEngine, FAQResponse
from app.models.session import Session as SessionModel


def _norm(text: str) -> str:
    """Lowercase, strip, remove diacritics."""
    t = (text or "").lower().strip()
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


SEGMENTO_MAP: dict[str, str] = {
    "corporativo": "corporativo", "corp": "corporativo",
    "empresa": "corporativo", "empresarial": "corporativo",
    "escritorio": "corporativo", "escritório": "corporativo",
    "saude": "saude", "saúde": "saude",
    "medico": "saude", "médico": "saude",
    "hospital": "saude", "clinica": "saude", "clínica": "saude",
    "jaleco": "saude", "odonto": "saude", "estetica": "saude",
    "industria": "industria", "indústria": "industria",
    "fabrica": "industria", "fábrica": "industria",
    "industrial": "industria",
    "domestica": "domestica", "doméstica": "domestica",
    "diarista": "domestica", "baba": "domestica", "babá": "domestica",
    "cuidadora": "domestica", "limpeza": "domestica",
    "outro": "outro", "outros": "outro", "outra": "outro",
    "nenhum": "outro", "diferente": "outro",
}


PERSONALIZACAO_MAP: dict[str, str] = {
    "bordado": "bordado", "bordar": "bordado", "borda": "bordado",
    "serigrafia": "serigrafia", "serigraf": "serigrafia",
    "estampa": "serigrafia", "silk": "serigrafia",
    "sem": "sem_personalizacao", "nenhum": "sem_personalizacao",
    "nenhuma": "sem_personalizacao", "nao": "sem_personalizacao",
    "não": "sem_personalizacao", "simples": "sem_personalizacao",
    "sem personalizacao": "sem_personalizacao",
    "sem_personalizacao": "sem_personalizacao",
}


CONFIRMACAO_MAP: dict[str, str] = {
    "confirmar": "confirmar", "confirmo": "confirmar",
    "sim": "confirmar", "s": "confirmar", "ok": "confirmar",
    "isso": "confirmar", "correto": "confirmar", "certo": "confirmar",
    "esta certo": "confirmar", "está certo": "confirmar",
    "pode ser": "confirmar", "pode": "confirmar",
    "corrigir": "corrigir", "corrige": "corrigir",
    "nao": "corrigir", "não": "corrigir", "errado": "corrigir",
    "mudar": "corrigir", "alterar": "corrigir", "voltar": "corrigir",
}


def _resolve_choice(text: str, mapping: dict[str, str]) -> str | None:
    """Tries exact match, then partial match against mapping keys.

    Partial match only for keys with len >= 3 — evita que "s"/"n"/"ok"
    casem trechos curtos de inputs longos como "saude" ou "ok comigo".
    """
    normalized = _norm(text)
    if normalized in mapping:
        return mapping[normalized]
    for key, val in mapping.items():
        if len(key) >= 3 and _norm(key) in normalized:
            return val
    return None


# Estados
INICIO = "inicio"
AGUARDA_NOME = "aguarda_nome"
MENU = "menu"
AGUARDA_PEDIDO = "aguarda_pedido"
ENVIA_CATALOGO = "envia_catalogo"
COLETA_ORCAMENTO_SEGMENTO = "coleta_orcamento_segmento"
COLETA_ORCAMENTO_PRODUTO = "coleta_orcamento_produto"
COLETA_ORCAMENTO_QTD = "coleta_orcamento_qtd"
COLETA_ORCAMENTO_PERSONALIZACAO = "coleta_orcamento_personalizacao"
COLETA_ORCAMENTO_PRAZO = "coleta_orcamento_prazo"
CONFIRMACAO_ORCAMENTO = "confirmacao_orcamento"
LEAD_CAPTURADO = "lead_capturado"
ENCAMINHAR_HUMANO = "encaminhar_humano"
AGUARDA_RETORNO_HUMANO = "aguarda_retorno_humano"
FIM = "fim"


KNOWN_STATES = {
    INICIO,
    AGUARDA_NOME,
    MENU,
    AGUARDA_PEDIDO,
    ENVIA_CATALOGO,
    COLETA_ORCAMENTO_SEGMENTO,
    COLETA_ORCAMENTO_PRODUTO,
    COLETA_ORCAMENTO_QTD,
    COLETA_ORCAMENTO_PERSONALIZACAO,
    COLETA_ORCAMENTO_PRAZO,
    CONFIRMACAO_ORCAMENTO,
    LEAD_CAPTURADO,
    ENCAMINHAR_HUMANO,
    AGUARDA_RETORNO_HUMANO,
    FIM,
}


HANDOFF_MESSAGE = (
    "👤 Estou te conectando com um dos nossos consultores!\n\n"
    "Nosso horário de atendimento é *segunda a sexta, das 8h às 18h*.\n"
    "Em breve alguém vai te responder aqui. 😊\n\n"
    "_Você pode continuar me fazendo perguntas enquanto aguarda._"
)


AGUARDA_RETORNO_MESSAGE = (
    "Já avisamos nossa equipe! Em breve um consultor vai te atender. 🕐\n\n"
    "Posso ajudar com mais alguma coisa enquanto isso?"
)


PRODUTOS_POR_SEGMENTO: dict[str, list[str]] = {
    "corporativo": ["Camisa Polo", "Básica Algodão"],
    "saude": ["Jaleco Tradicional", "Jaleco Premium"],
    "industria": ["Camisa Polo", "Básica PV"],
    "domestica": ["Uniforme Doméstica"],
    "outro": ["Camisa Polo", "Básica Algodão", "Regata"],
}


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


_ORCAMENTO_TRIGGERS = {
    "orcamento",
    "orçamento",
    "quero orcamento",
    "quero orçamento",
    "fazer orcamento",
    "fazer orçamento",
    "pedir orcamento",
    "pedir orçamento",
}


_SEGMENTO_LABELS: dict[str, str] = {
    "corporativo": "Corporativo",
    "saude": "Saúde",
    "industria": "Indústria",
    "domestica": "Doméstica",
    "outro": "Outro",
}


def _is_orcamento_trigger(text: str) -> bool:
    norm = text.lower().strip()
    if norm in _ORCAMENTO_TRIGGERS:
        return True
    if norm == "orcamento" or "orcamento" in norm or "orçamento" in norm:
        return True
    return False


def _segmento_list() -> FAQResponse:
    return FAQResponse(
        type="list",
        body="Para qual segmento é o uniforme?",
        list_button_label="Selecionar",
        list_items=[  # type: ignore[arg-type]
            {"id": "corporativo", "title": "Corporativo"},
            {"id": "saude", "title": "Saúde"},
            {"id": "industria", "title": "Indústria"},
            {"id": "domestica", "title": "Doméstica"},
            {"id": "outro", "title": "Outro"},
        ],
    )


def _produto_options(segmento_id: str) -> FAQResponse:
    produtos = PRODUTOS_POR_SEGMENTO.get(
        segmento_id, PRODUTOS_POR_SEGMENTO["outro"]
    )
    if len(produtos) <= 3:
        return FAQResponse(
            type="buttons",
            body="Qual produto você precisa?",
            buttons=[  # type: ignore[arg-type]
                {"id": p, "title": p[:20]} for p in produtos
            ],
        )
    return FAQResponse(
        type="list",
        body="Qual produto você precisa?",
        list_button_label="Ver produtos",
        list_items=[  # type: ignore[arg-type]
            {"id": p, "title": p[:24]} for p in produtos
        ],
    )


def _orcamento_resumo(session: SessionModel) -> FAQResponse:
    data = session.session_data or {}
    segmento = _SEGMENTO_LABELS.get(
        data.get("orcamento_segmento", ""), data.get("orcamento_segmento", "?")
    )
    produto = data.get("orcamento_produto", "?")
    quantidade = data.get("orcamento_quantidade", "?")
    personalizacao = data.get("orcamento_personalizacao", "?")
    prazo = data.get("orcamento_prazo", "?")
    body = (
        "📋 *Resumo do seu orçamento:*\n\n"
        f"• Segmento: {segmento}\n"
        f"• Produto: {produto}\n"
        f"• Quantidade: {quantidade} peças\n"
        f"• Personalização: {personalizacao}\n"
        f"• Prazo: {prazo}\n\n"
        "Está correto?"
    )
    return FAQResponse(
        type="buttons",
        body=body,
        buttons=[  # type: ignore[arg-type]
            {"id": "confirmar", "title": "✅ Confirmar"},
            {"id": "corrigir", "title": "✏️ Corrigir"},
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

    # ── Tenta FAQEngine em qualquer estado "aberto" ──────────────────────
    faq_match = faq_engine.match(texto) if texto else None

    # ── Escape hatch universal: /start reseta qualquer estado ───────────
    # Garante que o usuário NUNCA fique preso em nenhum estado.
    # start_command tem priority=100 no faq.json. Preserva contadores
    # de rate limit (rl_*) — esses não são workflow, são abuso-prevenção
    # e não devem ser bypassáveis via /start.
    if faq_match is not None and faq_match.intent_id == "start_command":
        data = session.session_data or {}
        preserved = {k: v for k, v in data.items() if k.startswith("rl_")}
        session.nome_cliente = None
        session.session_data = preserved
        return HandleResult(
            response=_text(_greeting(session, campaign_engine)),
            next_state=AGUARDA_NOME,
            matched_intent_id="start_command",
        )

    # ── Estado INICIO: envia saudação e avança para AGUARDA_NOME ──────────
    if estado_atual == INICIO:
        return HandleResult(
            response=_text(_greeting(session, campaign_engine)),
            next_state=AGUARDA_NOME,
        )

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
        # Intent explícito de orçamento tem precedência sobre FAQ
        if _is_orcamento_trigger(texto):
            return HandleResult(
                response=_segmento_list(),
                next_state=COLETA_ORCAMENTO_SEGMENTO,
            )

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

    if estado_atual == COLETA_ORCAMENTO_SEGMENTO:
        segmento_id = _resolve_choice(texto, SEGMENTO_MAP)
        if segmento_id is None:
            return HandleResult(
                response=_text(
                    "Não entendi. Para qual segmento é o uniforme?\n\n"
                    "1. Corporativo\n"
                    "2. Saúde\n"
                    "3. Indústria\n"
                    "4. Doméstica\n"
                    "5. Outro"
                ),
                next_state=COLETA_ORCAMENTO_SEGMENTO,
            )
        session.session_data["orcamento_segmento"] = segmento_id
        produtos = PRODUTOS_POR_SEGMENTO.get(
            segmento_id, PRODUTOS_POR_SEGMENTO["outro"]
        )
        if len(produtos) == 1:
            session.session_data["orcamento_produto"] = produtos[0]
            return HandleResult(
                response=_text(
                    f"Produto selecionado: *{produtos[0]}*\n\n"
                    "Quantas peças você precisa?"
                ),
                next_state=COLETA_ORCAMENTO_QTD,
            )
        return HandleResult(
            response=_produto_options(segmento_id),
            next_state=COLETA_ORCAMENTO_PRODUTO,
        )

    if estado_atual == COLETA_ORCAMENTO_PRODUTO:
        segmento_id = session.session_data.get("orcamento_segmento", "outro")
        produtos = PRODUTOS_POR_SEGMENTO.get(
            segmento_id, PRODUTOS_POR_SEGMENTO["outro"]
        )
        normalized_input = _norm(texto)
        produto_escolhido = None

        # Match por número (1, 2, 3...)
        if texto.strip().isdigit():
            idx = int(texto.strip()) - 1
            if 0 <= idx < len(produtos):
                produto_escolhido = produtos[idx]

        # Match parcial por nome
        if not produto_escolhido:
            for p in produtos:
                if _norm(p) in normalized_input or normalized_input in _norm(p):
                    produto_escolhido = p
                    break

        if not produto_escolhido:
            lista = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(produtos))
            return HandleResult(
                response=_text(f"Não encontrei esse produto. Escolha:\n\n{lista}"),
                next_state=COLETA_ORCAMENTO_PRODUTO,
            )

        session.session_data["orcamento_produto"] = produto_escolhido
        return HandleResult(
            response=_text(
                "Quantas peças você precisa? (ex: 10, 50, 200)"
            ),
            next_state=COLETA_ORCAMENTO_QTD,
        )

    if estado_atual == COLETA_ORCAMENTO_QTD:
        # Extrai o primeiro número da mensagem — aceita "12 peças",
        # "umas 50", "por volta de 30", "200 unidades", etc. [fix-Q1]
        import re as _re
        _match = _re.search(r"\d+", texto)
        if not _match:
            # Permite FAQ (ex.: endereço) interromper o fluxo sem perder contexto
            if faq_match is not None:
                return HandleResult(
                    response=faq_match.response,
                    next_state=COLETA_ORCAMENTO_QTD,
                    matched_intent_id=faq_match.intent_id,
                )
            return HandleResult(
                response=_text(
                    "Não entendi a quantidade 😊\n"
                    "Pode me dizer só o número?\n"
                    "Exemplo: 10, 50 ou 200"
                ),
                next_state=COLETA_ORCAMENTO_QTD,
            )
        qtd = int(_match.group())
        if qtd <= 0:
            return HandleResult(
                response=_text(
                    "A quantidade precisa ser maior que zero. Quantas peças?"
                ),
                next_state=COLETA_ORCAMENTO_QTD,
            )
        session.session_data["orcamento_quantidade"] = qtd
        return HandleResult(
            response=FAQResponse(
                type="buttons",
                body="Como deseja personalizar os uniformes?",
                buttons=[  # type: ignore[arg-type]
                    {"id": "bordado", "title": "🧵 Bordado"},
                    {"id": "serigrafia", "title": "🎨 Serigrafia"},
                    {"id": "sem_personalizacao", "title": "❌ Sem personalização"},
                ],
            ),
            next_state=COLETA_ORCAMENTO_PERSONALIZACAO,
        )

    if estado_atual == COLETA_ORCAMENTO_PERSONALIZACAO:
        personalizacao = _resolve_choice(texto, PERSONALIZACAO_MAP)
        if personalizacao is None:
            return HandleResult(
                response=_text(
                    "Como deseja personalizar?\n\n"
                    "1. Bordado\n"
                    "2. Serigrafia\n"
                    "3. Sem personalização"
                ),
                next_state=COLETA_ORCAMENTO_PERSONALIZACAO,
            )
        session.session_data["orcamento_personalizacao"] = personalizacao
        return HandleResult(
            response=_text(
                "Quando você precisa? (ex: 15 dias, urgente, sem pressa)"
            ),
            next_state=COLETA_ORCAMENTO_PRAZO,
        )

    if estado_atual == COLETA_ORCAMENTO_PRAZO:
        if not texto:
            return HandleResult(
                response=_text(
                    "Quando você precisa? (ex: 15 dias, urgente, sem pressa)"
                ),
                next_state=COLETA_ORCAMENTO_PRAZO,
            )
        session.session_data["orcamento_prazo"] = texto
        return HandleResult(
            response=_orcamento_resumo(session),
            next_state=CONFIRMACAO_ORCAMENTO,
        )

    if estado_atual == CONFIRMACAO_ORCAMENTO:
        escolha = _resolve_choice(texto, CONFIRMACAO_MAP)
        if escolha == "confirmar":
            nome = session.nome_cliente or "cliente"
            return HandleResult(
                response=FAQResponse(
                    type="buttons",
                    body=(
                        "✅ *Orçamento registrado!*\n\n"
                        f"Em breve um consultor vai entrar em contato com você, "
                        f"{nome}! 😊\n\n"
                        "Tem mais alguma dúvida?"
                    ),
                    buttons=[  # type: ignore[arg-type]
                        {"id": "menu", "title": "🏠 Menu principal"},
                        {"id": "falar_humano", "title": "🧑 Falar agora"},
                    ],
                ),
                next_state=LEAD_CAPTURADO,
                action="capture_lead",
            )
        if escolha == "corrigir":
            return HandleResult(
                response=_text(
                    "Sem problema! Quantas peças você precisa? (ex: 10, 50, 200)"
                ),
                next_state=COLETA_ORCAMENTO_QTD,
            )
        # Entrada ambígua — reapresentar resumo
        return HandleResult(
            response=_orcamento_resumo(session),
            next_state=CONFIRMACAO_ORCAMENTO,
        )

    if estado_atual == LEAD_CAPTURADO:
        escolha = texto.lower().strip()
        # Permite iniciar novo orçamento sem voltar manualmente ao menu
        if _is_orcamento_trigger(texto):
            return HandleResult(
                response=_segmento_list(),
                next_state=COLETA_ORCAMENTO_SEGMENTO,
            )
        if escolha in {"menu", "🏠 menu principal", "menu principal"}:
            return HandleResult(
                response=_menu_buttons(),
                next_state=MENU,
            )
        if escolha == "falar_humano":
            return HandleResult(
                response=_text(HANDOFF_MESSAGE),
                next_state=AGUARDA_RETORNO_HUMANO,
                action="forward_to_human",
            )
        if faq_match is not None:
            return HandleResult(
                response=faq_match.response,
                next_state=LEAD_CAPTURADO,
                matched_intent_id=faq_match.intent_id,
            )
        return HandleResult(
            response=_menu_buttons(),
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
            response=_text(HANDOFF_MESSAGE),
            next_state=AGUARDA_RETORNO_HUMANO,
            action="forward_to_human",
        )

    if estado_atual == AGUARDA_RETORNO_HUMANO:
        if faq_match is not None:
            return HandleResult(
                response=faq_match.response,
                next_state=faq_match.follow_up_state or AGUARDA_RETORNO_HUMANO,
                matched_intent_id=faq_match.intent_id,
            )
        return HandleResult(
            response=_text(AGUARDA_RETORNO_MESSAGE),
            next_state=AGUARDA_RETORNO_HUMANO,
        )

    if estado_atual == ENVIA_CATALOGO:
        return HandleResult(
            response=_menu_buttons(),
            next_state=MENU,
        )

    # Estado desconhecido — reseta para INICIO (defensive)
    return HandleResult(
        response=_text(_greeting(session, campaign_engine)),
        next_state=INICIO,
    )
