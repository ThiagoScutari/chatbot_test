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
from app.engines.regex_engine import FAQEngine, FAQMatch, FAQResponse
from app.models.session import Session as SessionModel


def _norm(text: str) -> str:
    """Lowercase, strip, remove diacritics."""
    t = (text or "").lower().strip()
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# [redesign-orcamento] Segmento agora é INFORMATIVO para o consultor —
# o bot nunca rejeita o que o cliente disser. Aliases mapeiam linguagem
# coloquial para o rótulo de exibição. Texto desconhecido vira "Outro
# (texto livre)" e segue o fluxo. Chaves já normalizadas (lowercase,
# sem acentos) — comparação via _norm.
SEGMENT_ALIASES: dict[str, str] = {
    # Rótulos canônicos (também são os ids dos botões da WhatsApp list)
    "corporativo": "Corporativo",
    "saude": "Saúde",
    "educacao": "Educação",
    "industria": "Indústria",
    "domestica": "Doméstica",
    "outro": "Outro",
    # Aliases — Educação
    "escolar": "Educação", "escola": "Educação", "faculdade": "Educação",
    "colegio": "Educação", "curso": "Educação", "professor": "Educação",
    "creche": "Educação",
    # Aliases — Corporativo
    "empresa": "Corporativo", "escritorio": "Corporativo",
    "loja": "Corporativo", "comercio": "Corporativo",
    "comercial": "Corporativo", "corp": "Corporativo",
    "empresarial": "Corporativo",
    # Aliases — Saúde
    "hospital": "Saúde", "clinica": "Saúde", "dentista": "Saúde",
    "medico": "Saúde", "consultorio": "Saúde", "odonto": "Saúde",
    "estetica": "Saúde", "enfermagem": "Saúde", "saude e estetica": "Saúde",
    # Aliases — Indústria
    "fabrica": "Indústria", "obra": "Indústria",
    "construcao": "Indústria", "industrial": "Indústria",
    "metalurgica": "Indústria",
    # Aliases — Doméstica
    "casa": "Doméstica", "baba": "Doméstica", "diarista": "Doméstica",
    "cuidadora": "Doméstica", "limpeza": "Doméstica",
}

# Mapa numeral exato (1..6) — corresponde à ordem do menu de segmento.
SEGMENT_NUMERAL: dict[str, str] = {
    "1": "Corporativo",
    "2": "Saúde",
    "3": "Educação",
    "4": "Indústria",
    "5": "Doméstica",
    "6": "Outro",
}

# Lista de produtos exibida sempre, independentemente do segmento.
TODOS_PRODUTOS: list[str] = [
    "Camisa Polo",
    "Camiseta Básica",
    "Regata",
    "Jaleco Tradicional",
    "Jaleco Premium",
    "Uniforme Industrial",
    "Uniforme Doméstico",
    "Boné Personalizado",
]

# Aliases para mapear linguagem livre → rótulo canônico do produto.
# Chaves normalizadas (_norm). Substring match só p/ chaves com len ≥ 4
# para evitar que numerais ("1", "2", ...) batam dentro de "100", "200".
PRODUTO_ALIASES: dict[str, str] = {
    # Camisa Polo
    "polo": "Camisa Polo",
    "camisa polo": "Camisa Polo",
    "polo piquet": "Camisa Polo",
    "piquet": "Camisa Polo",
    # Camiseta Básica
    "camiseta": "Camiseta Básica",
    "basica": "Camiseta Básica",
    "camiseta basica": "Camiseta Básica",
    "baby look": "Camiseta Básica",
    # Regata
    "regata": "Regata",
    # Jaleco Tradicional / Premium (premium primeiro p/ specificidade,
    # mas a iteração por len decrescente já garante isso)
    "jaleco tradicional": "Jaleco Tradicional",
    "jaleco premium": "Jaleco Premium",
    "jaleco": "Jaleco Tradicional",
    # Uniforme Industrial
    "uniforme industrial": "Uniforme Industrial",
    "industrial": "Uniforme Industrial",
    # Uniforme Doméstico
    "uniforme domestico": "Uniforme Doméstico",
    "domestico": "Uniforme Doméstico",
    # Boné
    "bone personalizado": "Boné Personalizado",
    "bone": "Boné Personalizado",
    "bones": "Boné Personalizado",
}

PRODUTO_NUMERAL: dict[str, str] = {
    "1": "Camisa Polo",
    "2": "Camiseta Básica",
    "3": "Regata",
    "4": "Jaleco Tradicional",
    "5": "Jaleco Premium",
    "6": "Uniforme Industrial",
    "7": "Uniforme Doméstico",
    "8": "Boné Personalizado",
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
    "1": "confirmar", "✅": "confirmar",
    "confirmar": "confirmar", "confirmo": "confirmar",
    "sim": "confirmar", "s": "confirmar", "ok": "confirmar",
    "yes": "confirmar",
    "isso": "confirmar", "correto": "confirmar", "certo": "confirmar",
    "esta certo": "confirmar", "está certo": "confirmar",
    "pode ser": "confirmar", "pode": "confirmar",
    "exato": "confirmar", "bora": "confirmar", "manda ver": "confirmar",
    "2": "corrigir", "✏️": "corrigir",
    "corrigir": "corrigir", "corrige": "corrigir",
    "nao": "corrigir", "não": "corrigir", "errado": "corrigir",
    "no": "corrigir", "n": "corrigir",
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
COLETA_BORDADO_INFO = "coleta_bordado_info"
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
    COLETA_BORDADO_INFO,
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


def _check_escape(faq_match: FAQMatch | None) -> "HandleResult | None":
    """Escape hatch: falar_humano interrompe qualquer fluxo de coleta.

    Sem isso o usuário fica preso aguardando input estruturado (segmento,
    quantidade, prazo) sem opção visível de sair. [fix-bug3]
    """
    if faq_match is not None and faq_match.intent_id == "falar_humano":
        return HandleResult(
            response=faq_match.response,
            next_state=AGUARDA_RETORNO_HUMANO,
            matched_intent_id="falar_humano",
            action="forward_to_human",
        )
    return None


def _menu_buttons() -> FAQResponse:
    # [fix-4] Menu unificado — mesmo conjunto e ordem em todos os pontos do
    # bot (aguarda_nome, fallback de FAQ, retorno do catálogo, lead capturado).
    return FAQResponse(
        type="buttons",
        body="Como posso te ajudar?",
        buttons=[  # type: ignore[arg-type]
            {"id": "orcamento", "title": "💰 Fazer orçamento"},
            {"id": "ver_catalogo", "title": "👕 Ver catálogo"},
            {"id": "consultar_pedido", "title": "📦 Meu pedido"},
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


# [fix-1] Saudações comuns não devem ser aceitas como nome em AGUARDA_NOME.
# Sem este filtro, o cliente que envia "Olá" após /start vê "Prazer, Olá! Como
# posso te ajudar?" — confuso e quebra o onboarding.
_GREETINGS = {
    "oi", "ola", "ola!", "bom dia", "boa tarde", "boa noite",
    "eae", "eai", "e ai", "e aí", "fala", "salve", "opa", "opa!",
    "hey", "hello", "hi", "ei", "olá",
}


# [fix-3] Frases curtas de "nada mais" em AGUARDA_RETORNO_HUMANO. Match exato
# após _norm (lower + sem acentos). Frases mais longas usam _NEGATIVE_TOKENS.
_NEGATIVE_RESPONSES = {
    "nao", "n", "no", "nope", "nada", "nenhuma", "nenhum",
    "ta bom", "ta", "tah", "ok", "okay", "beleza", "blz",
    "obrigado", "obrigada", "valeu", "vlw", "tamo junto", "tmj",
    "tchau", "flw", "falou", "ate logo", "ate", "ja era",
    "ja falei que nao", "nao preciso", "aff", "ufa",
}

# Tokens que, presentes em qualquer parte da mensagem, indicam intenção
# negativa de continuar a conversa (sem ter que enumerar variações).
_NEGATIVE_TOKENS = {"nao", "tchau", "obrigad", "valeu", "aff", "nada"}


def _is_orcamento_trigger(text: str) -> bool:
    norm = text.lower().strip()
    if norm in _ORCAMENTO_TRIGGERS:
        return True
    if norm == "orcamento" or "orcamento" in norm or "orçamento" in norm:
        return True
    return False


def _segmento_list() -> FAQResponse:
    # [redesign-orcamento] Educação adicionada como 3º item — escolas, creches
    # e cursos eram capturadas em "Outro" sem visibilidade adequada.
    return FAQResponse(
        type="list",
        body=(
            "Para qual segmento é o uniforme? "
            "(Pode escolher pelo número ou descrever.)"
        ),
        list_button_label="Selecionar",
        list_items=[  # type: ignore[arg-type]
            {"id": "corporativo", "title": "Corporativo"},
            {"id": "saude", "title": "Saúde"},
            {"id": "educacao", "title": "Educação"},
            {"id": "industria", "title": "Indústria"},
            {"id": "domestica", "title": "Doméstica"},
            {"id": "outro", "title": "Outro"},
        ],
    )


def _todos_produtos_prompt(segmento: str) -> FAQResponse:
    """Lista TODOS os produtos disponíveis após captura de segmento.

    [redesign-orcamento] Antes filtrávamos produtos por segmento via
    PRODUTOS_POR_SEGMENTO — quem vinha de "Educação" não via "Camisa Polo",
    quem vinha de "Outro (pet shop)" não via nada. Agora todo cliente vê
    os 8 produtos e ainda pode escrever livremente.
    """
    if segmento.startswith("Outro ("):
        intro = "Anotado! 📋"
    else:
        intro = f"Ótimo, *{segmento}*! 📋"
    return _text(
        f"{intro}\n\n"
        "O que você gostaria de fazer?\n\n"
        "Nossos principais produtos:\n"
        "1. 👕 Camisa Polo\n"
        "2. 👕 Camiseta Básica\n"
        "3. 💪 Regata\n"
        "4. 🥼 Jaleco Tradicional\n"
        "5. 🥼 Jaleco Premium\n"
        "6. 🏭 Uniforme Industrial\n"
        "7. 👗 Uniforme Doméstico\n"
        "8. 🧢 Boné Personalizado\n\n"
        "Pode escolher pelo número ou descrever o que precisa "
        "— mesmo que não esteja na lista! 😊"
    )


def _resolve_segment(text: str) -> str:
    """Resolve a entrada do cliente para um rótulo de segmento.

    Nunca retorna None. Se não bater nenhum alias/numeral, devolve
    "Outro (texto livre)" — preserva o que o cliente escreveu para o
    consultor humano.
    """
    norm = _norm(text)
    if not norm:
        return "Outro"
    # 1. Match exato no alias
    if norm in SEGMENT_ALIASES:
        return SEGMENT_ALIASES[norm]
    # 2. Numeral exato
    if norm in SEGMENT_NUMERAL:
        return SEGMENT_NUMERAL[norm]
    # 3. Substring — chaves longas primeiro p/ specificidade.
    #    Filtro len ≥ 4 evita falsos positivos com palavras curtas.
    for key in sorted(SEGMENT_ALIASES.keys(), key=len, reverse=True):
        if len(key) >= 4 and key in norm:
            return SEGMENT_ALIASES[key]
    # 4. Texto livre — armazena com prefixo "Outro (...)"
    return f"Outro ({text.strip()})"


def _resolve_produto(text: str) -> str:
    """Resolve a entrada do cliente para um produto.

    Match APENAS exato (alias ou numeral). Descrições livres como
    "camiseta estampada com logo da escola" são preservadas como
    vieram — o consultor lê o resumo e entende o pedido completo.
    Substring match aqui prejudicaria descrições ricas (ex.: substring
    "camiseta" em texto longo vira só "Camiseta Básica" e perde detalhe).
    """
    norm = _norm(text)
    if not norm:
        return text.strip()
    # 1. Numeral exato (1..8)
    if norm in PRODUTO_NUMERAL:
        return PRODUTO_NUMERAL[norm]
    # 2. Match exato em alias
    if norm in PRODUTO_ALIASES:
        return PRODUTO_ALIASES[norm]
    # 3. Texto livre — preserva como veio
    return text.strip()


def _orcamento_resumo(session: SessionModel) -> FAQResponse:
    data = session.session_data or {}
    # [redesign-orcamento] segmento agora é o próprio rótulo de exibição
    # (ex.: "Saúde", "Outro (pet shop)"), sem necessidade de lookup.
    segmento = data.get("orcamento_segmento") or "?"
    produto = data.get("orcamento_produto", "?")
    quantidade = data.get("orcamento_quantidade", "?")
    personalizacao = data.get("orcamento_personalizacao", "?")
    prazo = data.get("orcamento_prazo", "?")
    arte_label_map = {
        "tem_arte": "Arte disponível",
        "precisa_criar": "Precisa criar a arte",
        "nao_sabe": "A confirmar com consultor",
    }
    bordado_arte = data.get("bordado_arte")
    arte_line = ""
    if bordado_arte:
        arte_line = (
            f"• Arte para bordado: "
            f"{arte_label_map.get(bordado_arte, bordado_arte)}\n"
        )
    body = (
        "📋 *Resumo do seu orçamento:*\n\n"
        f"• Segmento: {segmento}\n"
        f"• Produto: {produto}\n"
        f"• Quantidade: {quantidade} peças\n"
        f"• Personalização: {personalizacao}\n"
        f"{arte_line}"
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
        # [fix-U1] Se a sessão já tem nome (estado dessincronizado, /start
        # parcial ou loop entre estados), não pergunta de novo — re-roteia
        # a mensagem como se viesse do MENU para que o intent atual seja
        # processado normalmente. Sem isso, intents com follow_up_state
        # (ex.: orçamento) deixavam o usuário preso em AGUARDA_NOME.
        if session.nome_cliente:
            session.current_state = MENU
            return handle(message, session, faq_engine, campaign_engine)
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
        # [fix-1] Saudações ("Olá", "oi", "bom dia") não são nomes — re-pergunta
        # de forma educada em vez de gravar a saudação como nome do cliente.
        if _norm(texto) in _GREETINGS:
            return HandleResult(
                response=_text(
                    "Olá! 😊 Para te atender melhor, me diz o seu nome?"
                ),
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
                    {"id": "orcamento", "title": "💰 Fazer orçamento"},
                    {"id": "ver_catalogo", "title": "👕 Ver catálogo"},
                    {"id": "consultar_pedido", "title": "📦 Meu pedido"},
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
            "1": "orcamento",
            "2": "ver_catalogo",
            "3": "consultar_pedido",
            "4": "falar_humano",
        }
        acao_id = menu_alias.get(texto, texto)

        if acao_id == "orcamento":
            return HandleResult(
                response=_segmento_list(),
                next_state=COLETA_ORCAMENTO_SEGMENTO,
            )
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
        escape = _check_escape(faq_match)
        if escape:
            return escape
        # [redesign-orcamento] NUNCA rejeita o segmento — _resolve_segment
        # devolve "Outro (texto livre)" para entradas desconhecidas e o fluxo
        # avança. Segmento é informativo para o consultor humano.
        segmento = _resolve_segment(texto)
        session.session_data["orcamento_segmento"] = segmento
        return HandleResult(
            response=_todos_produtos_prompt(segmento),
            next_state=COLETA_ORCAMENTO_PRODUTO,
        )

    if estado_atual == COLETA_ORCAMENTO_PRODUTO:
        escape = _check_escape(faq_match)
        if escape:
            return escape
        # [redesign-orcamento] NUNCA rejeita o produto — texto livre é
        # preservado como veio. Casos suportados:
        # - "1" → "Camisa Polo" (numeral)
        # - "polo" → "Camisa Polo" (alias)
        # - "uniforme com saia bordada" → texto livre, armazenado como veio
        produto = _resolve_produto(texto)
        session.session_data["orcamento_produto"] = produto
        return HandleResult(
            response=_text(
                "Quantas peças você precisa? (ex: 10, 50, 200)"
            ),
            next_state=COLETA_ORCAMENTO_QTD,
        )

    if estado_atual == COLETA_ORCAMENTO_QTD:
        escape = _check_escape(faq_match)
        if escape:
            return escape
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
        escape = _check_escape(faq_match)
        if escape:
            return escape
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
        # [fix-Q3] Quando bordado: coleta info de arte antes de pedir prazo
        if personalizacao == "bordado":
            return HandleResult(
                response=_text(
                    "🧵 *Bordado Camisart:*\n"
                    "• A partir de 1 peça — sem pedido mínimo\n"
                    "• Prazo: 5 a 7 dias úteis\n"
                    "• Programação da arte: R$ 60 a R$ 80 (cobrado 1x)\n"
                    "• Por peça (7 a 9 cm): R$ 4,50/bordado\n\n"
                    "Você já tem a arte/logo pronta?\n\n"
                    "1. ✅ Sim, tenho o arquivo\n"
                    "2. 🎨 Preciso criar a arte\n"
                    "3. ❌ Ainda não sei"
                ),
                next_state=COLETA_BORDADO_INFO,
            )
        return HandleResult(
            response=_text(
                "Quando você precisa? (ex: 15 dias, urgente, sem pressa)"
            ),
            next_state=COLETA_ORCAMENTO_PRAZO,
        )

    if estado_atual == COLETA_BORDADO_INFO:
        escape = _check_escape(faq_match)
        if escape:
            return escape
        arte_map = {
            "1": "tem_arte",
            "sim": "tem_arte",
            "tenho": "tem_arte",
            "tenho o arquivo": "tem_arte",
            "tenho a arte": "tem_arte",
            "✅": "tem_arte",
            "2": "precisa_criar",
            "nao tenho": "precisa_criar",
            "não tenho": "precisa_criar",
            "preciso criar": "precisa_criar",
            "criar": "precisa_criar",
            "🎨": "precisa_criar",
            "3": "nao_sabe",
            "nao sei": "nao_sabe",
            "não sei": "nao_sabe",
            "ainda nao sei": "nao_sabe",
            "❌": "nao_sabe",
        }
        texto_norm = _norm(texto)
        arte = arte_map.get(texto_norm)
        if arte is None:
            for key, val in arte_map.items():
                if len(key) >= 3 and _norm(key) in texto_norm:
                    arte = val
                    break
        if arte is None:
            arte = texto_norm if texto_norm else "nao_informado"
        session.session_data["bordado_arte"] = arte

        if arte == "tem_arte":
            msg = (
                "Ótimo! Envie a arte para nosso consultor "
                "nos formatos: *AI, CDR, PDF vetorial ou PNG 300dpi*. 😊\n\n"
                "Quando você precisa? (ex: 15 dias, urgente, sem pressa)"
            )
        elif arte == "precisa_criar":
            msg = (
                "Sem problema! Temos designer próprio para criar sua arte. 🎨\n"
                "O consultor vai passar os detalhes e o valor.\n\n"
                "Quando você precisa? (ex: 15 dias, urgente, sem pressa)"
            )
        elif arte == "nao_sabe":
            msg = (
                "Tudo bem! O consultor vai te ajudar com isso. 😊\n\n"
                "Quando você precisa? (ex: 15 dias, urgente, sem pressa)"
            )
        else:
            msg = (
                "Anotado. O consultor vai esclarecer com você.\n\n"
                "Quando você precisa? (ex: 15 dias, urgente, sem pressa)"
            )
        return HandleResult(
            response=_text(msg),
            next_state=COLETA_ORCAMENTO_PRAZO,
        )

    if estado_atual == COLETA_ORCAMENTO_PRAZO:
        escape = _check_escape(faq_match)
        if escape:
            return escape
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
        escape = _check_escape(faq_match)
        if escape:
            return escape
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
        # [fix-3] Negações ("não", "tchau", "nada", "obrigado") encerram o
        # ping-pong "Posso ajudar com mais alguma coisa?". Sem este filtro o
        # bot insiste com o mesmo prompt indefinidamente, mesmo após o cliente
        # já ter dito que não precisa de mais nada.
        texto_norm = _norm(texto)
        is_negative = (
            texto_norm in _NEGATIVE_RESPONSES
            or any(tok in texto_norm for tok in _NEGATIVE_TOKENS)
        )
        if is_negative:
            return HandleResult(
                response=_text(
                    "Tudo bem! 😊 Se precisar de algo, é só me chamar.\n\n"
                    "Um consultor entrará em contato em breve.\n"
                    "Obrigado pela preferência — Camisart Belém! 🧵"
                ),
                next_state=AGUARDA_RETORNO_HUMANO,
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
