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
CONVERSA_FINALIZADA = "conversa_finalizada"
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
    CONVERSA_FINALIZADA,
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


# IDs canônicos de botões — quando o canal envia um click de botão, o id
# vem como texto literal (ex.: "ver_catalogo"). O interceptor global de
# linguagem natural (catálogo / menu) precisa pular esses casos para que
# o handler de estado faça o despacho canônico (ex.: send_catalog action).
_CHANNEL_BUTTON_IDS = frozenset({
    "ver_catalogo", "consultar_pedido", "orcamento", "menu",
})


# ── Triggers do interceptor global ───────────────────────────────────────
# Texto natural — comparado em substring sobre texto_lower (sem acento via
# _norm quando necessário). Mantidos como tuplas para velocidade.

_HUMANO_TRIGGERS: tuple[str, ...] = (
    "falar com atendente", "falar com humano",
    "falar c humano", "falar c/ atendente",
    "quero falar com alguem", "quero falar com alguém",
    "me passa pra um humano", "atendente",
    "falar com um atendente", "humano",
)

_FINALIZAR_TRIGGERS: tuple[str, ...] = (
    "finalizar", "encerrar", "fechar",
    "finalizar conversa", "encerrar conversa",
    "finalizar atendimento", "encerrar atendimento",
    "era só isso", "era isso", "só isso",
    "por enquanto é isso", "por enquanto é só",
)

_MENU_TRIGGERS: tuple[str, ...] = (
    "menu", "voltar", "voltar ao menu",
    "menu principal", "início", "inicio",
)

_CATALOGO_TRIGGERS: tuple[str, ...] = (
    "ver catálogo", "ver catalogo", "catálogo", "catalogo",
    "ver produtos", "produtos",
    "o que vocês tem", "o que vcs tem",
    "quero ver o catálogo",
)

# Estados pós-atendimento — onde negativos isolados ("não", "tchau") devem
# encerrar a conversa em vez de manter o ping-pong de "posso ajudar?"
_POS_ATENDIMENTO_STATES = frozenset({
    LEAD_CAPTURADO,
    AGUARDA_RETORNO_HUMANO,
    CONVERSA_FINALIZADA,
})

_NEGATIVE_EXATO_NORM = {
    "nao", "n", "nada", "tchau", "flw",
    "valeu", "vlw", "obrigado", "obrigada",
    "ok", "ta bom", "beleza",
    "aff", "ja falei", "nenhuma", "nenhum",
}

# Substring tokens — "ja falei que nao", "obrigado pela atencao", etc.
_NEGATIVE_TOKEN_SUBSTRINGS = ("nao", "tchau", "obrigad", "valeu", "aff", "nada")


def _global_intercept(
    texto: str,
    texto_lower: str,
    estado_atual: str,
    session: SessionModel,
    faq_match: FAQMatch | None,
    campaign_engine: CampaignEngine | None,
) -> "HandleResult | None":
    """Intercepta comportamentos globais ANTES do handler de estado.

    Substitui o antigo `_check_escape` per-state: comportamentos como
    "/start", "falar com humano", "finalizar", "ver catálogo" e "menu"
    funcionam universalmente, sem precisar repetir lógica em cada handler.

    Retorna `HandleResult` se a mensagem foi interceptada; `None` se o
    handler de estado deve continuar normalmente.

    Ordem de prioridade:
      1. /start  — reset universal preservando contadores rl_*
      2. Falar com humano (FAQ ou triggers livres)
      3. Finalizar conversa
      4. Negação pós-atendimento (LEAD/HUMANO/FINALIZADA)
      5. Voltar ao menu
      6. Ver catálogo
    """
    # ── 1. /start — reset universal ──────────────────────────────
    if texto == "/start":
        data = session.session_data or {}
        preserved = {k: v for k, v in data.items() if k.startswith("rl_")}
        session.nome_cliente = None
        session.session_data = preserved
        return HandleResult(
            response=_text(_greeting(session, campaign_engine)),
            next_state=AGUARDA_NOME,
            matched_intent_id="start_command",
        )

    is_button_id = texto_lower in _CHANNEL_BUTTON_IDS

    # ── 2. Falar com humano (qualquer estado exceto AGUARDA_NOME) ─
    if estado_atual != AGUARDA_NOME:
        humano_via_faq = (
            faq_match is not None and faq_match.intent_id == "falar_humano"
        )
        humano_via_text = any(t in texto_lower for t in _HUMANO_TRIGGERS)
        if humano_via_faq or humano_via_text:
            response = (
                faq_match.response if humano_via_faq else _text(
                    "👤 Vou te conectar com um consultor!\n\n"
                    "Atendimento: *segunda a sexta, 8h às 18h*.\n"
                    "Em breve alguém vai te responder. 😊"
                )
            )
            return HandleResult(
                response=response,
                next_state=AGUARDA_RETORNO_HUMANO,
                matched_intent_id="falar_humano",
                action="forward_to_human",
            )

    # ── 3. Finalizar conversa ────────────────────────────────────
    if any(t in texto_lower for t in _FINALIZAR_TRIGGERS):
        nome = session.nome_cliente or ""
        prefix = f", {nome}" if nome else ""
        return HandleResult(
            response=_text(
                f"Obrigado pelo contato{prefix}! 😊\n\n"
                "Se precisar de algo, é só me chamar.\n"
                "Camisart Belém — sua loja de uniformes! 🧵"
            ),
            next_state=CONVERSA_FINALIZADA,
            matched_intent_id="finalizar_conversa",
        )

    # ── 4. Negação pós-atendimento ───────────────────────────────
    if estado_atual in _POS_ATENDIMENTO_STATES:
        texto_norm = _norm(texto)
        is_negative = (
            texto_norm in _NEGATIVE_EXATO_NORM
            or any(tok in texto_norm for tok in _NEGATIVE_TOKEN_SUBSTRINGS)
        )
        if is_negative:
            nome = session.nome_cliente or ""
            prefix = f", {nome}" if nome else ""
            return HandleResult(
                response=_text(
                    f"Tudo bem{prefix}! 😊\n\n"
                    "Se precisar de algo, é só me chamar.\n"
                    "Camisart Belém — sua loja de uniformes! 🧵"
                ),
                next_state=CONVERSA_FINALIZADA,
            )

    # ── 5. Voltar ao menu ────────────────────────────────────────
    # Exceção CONFIRMACAO_ORCAMENTO: "voltar" lá significa "corrigir"
    # (CONFIRMACAO_MAP), não "ir pro menu". O handler do estado lida.
    if (
        estado_atual not in (AGUARDA_NOME, CONFIRMACAO_ORCAMENTO)
        and any(t in texto_lower for t in _MENU_TRIGGERS)
    ):
        return HandleResult(
            response=_menu_buttons(),
            next_state=MENU,
        )

    # ── 6. Ver catálogo ──────────────────────────────────────────
    # Pula button id ("ver_catalogo") — o handler do MENU envia o PDF
    # via action=send_catalog. Texto natural recebe versão em texto.
    if (
        estado_atual != AGUARDA_NOME
        and not is_button_id
        and any(t in texto_lower for t in _CATALOGO_TRIGGERS)
    ):
        return HandleResult(
            response=_text(
                "👕 *Catálogo Camisart Belém:*\n\n"
                "• Camisa Polo — a partir de R$ 42,00\n"
                "• Camiseta Básica — a partir de R$ 25,00\n"
                "• Regata — a partir de R$ 20,00\n"
                "• Jaleco Tradicional — R$ 120,00\n"
                "• Jaleco Premium — R$ 145,00\n"
                "• Uniforme Industrial — A consultar\n"
                "• Uniforme Doméstico — R$ 120,00\n"
                "• Boné Personalizado — R$ 35,00\n"
                "• 🇧🇷 Polo Copa do Brasil — R$ 50,00\n\n"
                "Quer saber mais sobre algum produto?\n"
                "Ou deseja fazer um orçamento? 😊"
            ),
            next_state=MENU,
            matched_intent_id="ver_catalogo",
        )

    # Não interceptado — handler de estado prossegue
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
    texto_lower = texto.lower()

    # ── Tenta FAQEngine em qualquer estado "aberto" ──────────────────────
    faq_match = faq_engine.match(texto) if texto else None

    # ════════════════════════════════════════════════════════════════════
    # GLOBAL INTERCEPTOR — comportamentos que devem funcionar em qualquer
    # estado (escape hatches universais). Roda ANTES dos handlers per-state
    # e substitui o antigo `_check_escape` espalhado pelos coleta_*.
    # ════════════════════════════════════════════════════════════════════
    intercepted = _global_intercept(
        texto, texto_lower, estado_atual, session, faq_match, campaign_engine
    )
    if intercepted is not None:
        return intercepted

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
        # Negativos / "menu" / "falar com humano" / "finalizar" / "catálogo"
        # já foram interceptados em _global_intercept. Aqui sobra:
        # - novo orçamento
        # - FAQ de conhecimento (preço, prazo, etc.)
        # - qualquer outro input → de volta ao menu
        if _is_orcamento_trigger(texto):
            return HandleResult(
                response=_segmento_list(),
                next_state=COLETA_ORCAMENTO_SEGMENTO,
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

    if estado_atual == CONVERSA_FINALIZADA:
        # Qualquer mensagem nova reabre a conversa. Negativos isolados são
        # absorvidos pelo _global_intercept antes de chegar aqui.
        if session.nome_cliente:
            return HandleResult(
                response=_menu_buttons(),
                next_state=MENU,
            )
        return HandleResult(
            response=_text(
                "Olá de novo! 😊\n\n"
                "Com quem tenho o prazer?"
            ),
            next_state=AGUARDA_NOME,
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
        # Negativos ("não", "tchau", "obrigado", "aff") são capturados pelo
        # _global_intercept e levam para CONVERSA_FINALIZADA. Aqui só sobra
        # FAQ de conhecimento (endereço, preço, etc.) ou texto livre.
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
