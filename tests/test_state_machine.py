"""Testes da lógica do state_machine.handle()."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.engines.campaign_engine import CampaignEngine
from app.engines.regex_engine import FAQEngine
from app.engines.state_machine import (
    AGUARDA_NOME,
    AGUARDA_PEDIDO,
    ENCAMINHAR_HUMANO,
    ENVIA_CATALOGO,
    INICIO,
    MENU,
    handle,
)
from app.models.session import Session as SessionModel


FAQ_PATH = Path("app/knowledge/faq.json")


@pytest.fixture
def faq_engine():
    return FAQEngine(FAQ_PATH)


@pytest.fixture
def faq():
    """Alias usado pelos testes de cobertura do S02-06."""
    return FAQEngine(FAQ_PATH)


@pytest.fixture
def campaign_engine():
    ce = CampaignEngine(Path("app/knowledge/campaigns.json"))
    ce.reload()
    return ce


def _sess(estado: str = INICIO) -> SessionModel:
    s = SessionModel(
        channel_id="telegram",
        channel_user_id="5591999990099",
    )
    s.current_state = estado
    s.session_data = {}
    return s


def make_session(
    state: str,
    nome: str | None = None,
    data: dict | None = None,
) -> MagicMock:
    s = MagicMock()
    s.current_state = state
    s.nome_cliente = nome
    s.session_data = data if data is not None else {}
    return s


# ── Testes originais (SessionModel real) ──────────────────────────────────


def test_inicio_envia_saudacao(faq_engine, campaign_engine):
    r = handle("olá", _sess(INICIO), faq_engine, campaign_engine)
    assert r.next_state == AGUARDA_NOME
    assert "bem-vindo" in r.response.body.lower()


def test_aguarda_nome_salva_e_vai_para_menu(faq_engine, campaign_engine):
    s = _sess(AGUARDA_NOME)
    r = handle("Thiago", s, faq_engine, campaign_engine)
    assert r.next_state == MENU
    assert s.nome_cliente == "Thiago"
    assert r.response.type == "buttons"


def test_menu_alias_numerico_1_inicia_orcamento(faq_engine, campaign_engine):
    # [fix-Q4] menu reordenado: 1=orçamento, 2=catálogo, 3=pedido, 4=humano
    r = handle("1", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == "coleta_orcamento_segmento"


def test_menu_alias_numerico_2_dispara_catalogo(faq_engine, campaign_engine):
    r = handle("2", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == ENVIA_CATALOGO
    assert r.action == "send_catalog"


def test_menu_alias_numerico_3_vai_para_aguarda_pedido(faq_engine, campaign_engine):
    r = handle("3", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == AGUARDA_PEDIDO


def test_menu_alias_numerico_4_encaminha_humano(faq_engine, campaign_engine):
    r = handle("4", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == ENCAMINHAR_HUMANO
    assert r.action == "forward_to_human"


def test_menu_button_id_original_continua_funcionando(faq_engine, campaign_engine):
    r = handle("consultar_pedido", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == AGUARDA_PEDIDO


def test_menu_fallback_quando_sem_match(faq_engine, campaign_engine):
    r = handle("qualquer_coisa_xyz", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == MENU
    assert r.response.type == "buttons"


def test_aguarda_pedido_texto_nao_numerico_permanece(faq_engine, campaign_engine):
    r = handle("abc", _sess(AGUARDA_PEDIDO), faq_engine, campaign_engine)
    assert r.next_state == AGUARDA_PEDIDO
    assert "inválido" in r.response.body.lower()


# ── Testes S02-06: cobertura ampla com MagicMock ──────────────────────────

# 1. INICIO
def test_inicio_returns_greeting(faq):
    s = make_session("inicio")
    r = handle("oi", s, faq)
    assert r.next_state == "aguarda_nome"
    assert r.response.body


# 2. AGUARDA_NOME
def test_aguarda_nome_saves_name(faq):
    s = make_session("aguarda_nome")
    r = handle("Maria", s, faq)
    assert r.next_state == "menu"
    assert s.nome_cliente == "Maria"


# 3. MENU → consultar pedido
def test_menu_consultar_pedido(faq):
    s = make_session("menu", nome="Maria")
    r = handle("consultar_pedido", s, faq)
    assert r.next_state == "aguarda_pedido"


def test_menu_numeral_1(faq):
    # [fix-Q4] 1 agora inicia orçamento
    s = make_session("menu", nome="Maria")
    r = handle("1", s, faq)
    assert r.next_state == "coleta_orcamento_segmento"


# 4. MENU → catálogo
def test_menu_catalogo(faq):
    s = make_session("menu", nome="Maria")
    r = handle("ver_catalogo", s, faq)
    assert r.next_state == "envia_catalogo"
    assert r.action == "send_catalog"


def test_menu_numeral_2(faq):
    s = make_session("menu", nome="Maria")
    r = handle("2", s, faq)
    assert r.action == "send_catalog"


# 5. MENU → humano
# [state-redesign] O global interceptor captura "falar_humano" via FAQ
# match e vai DIRETO para aguarda_retorno_humano, sem o estado intermediário
# ENCAMINHAR_HUMANO (que era apenas um passo redundante).
def test_menu_humano(faq):
    s = make_session("menu", nome="Maria")
    r = handle("falar_humano", s, faq)
    assert r.next_state == "aguarda_retorno_humano"
    assert r.action == "forward_to_human"


def test_menu_numeral_3(faq):
    # [fix-Q4] 3 agora vai para consultar pedido
    s = make_session("menu", nome="Maria")
    r = handle("3", s, faq)
    assert r.next_state == "aguarda_pedido"


def test_menu_numeral_4(faq):
    s = make_session("menu", nome="Maria")
    r = handle("4", s, faq)
    assert r.action == "forward_to_human"


# 6. MENU → FAQ high priority
def test_menu_faq_match_keeps_state(faq):
    s = make_session("menu", nome="Maria")
    r = handle("qual o preço da polo?", s, faq)
    assert (
        r.matched_intent_id == "preco_polo"
        or "polo" in r.response.body.lower()
    )
    assert r.next_state == "menu"


# 7. MENU → fallback
def test_menu_no_match_fallback(faq):
    s = make_session("menu", nome="Maria")
    r = handle("xablau foobar inexistente", s, faq)
    assert r.next_state == "menu"
    assert r.response.body


# 8. ENCAMINHAR_HUMANO → moves to AGUARDA_RETORNO_HUMANO
def test_encaminhar_humano_state(faq):
    s = make_session("encaminhar_humano", nome="Maria")
    r = handle("qualquer coisa", s, faq)
    assert r.next_state == "aguarda_retorno_humano"
    assert r.action == "forward_to_human"


# 9. AGUARDA_RETORNO_HUMANO + FAQ match
def test_aguarda_retorno_faq_match(faq):
    s = make_session("aguarda_retorno_humano", nome="Maria")
    r = handle("qual o endereço?", s, faq)
    assert r.next_state == "aguarda_retorno_humano"
    assert (
        "Magalhães" in r.response.body
        or r.matched_intent_id == "endereco"
    )


# 10. AGUARDA_RETORNO_HUMANO + no match
def test_aguarda_retorno_no_match(faq):
    s = make_session("aguarda_retorno_humano", nome="Maria")
    r = handle("xablau", s, faq)
    assert r.next_state == "aguarda_retorno_humano"


# 11. COLETA_ORCAMENTO_QTD — quantidade inválida
def test_qtd_invalida_mantem_estado(faq):
    s = make_session(
        "coleta_orcamento_qtd",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
        },
    )
    r = handle("muitas", s, faq)
    assert r.next_state == "coleta_orcamento_qtd"


def test_qtd_zero_mantem_estado(faq):
    s = make_session(
        "coleta_orcamento_qtd",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
        },
    )
    r = handle("0", s, faq)
    assert r.next_state == "coleta_orcamento_qtd"


def test_qtd_valida_avanca(faq):
    s = make_session(
        "coleta_orcamento_qtd",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
        },
    )
    r = handle("50", s, faq)
    assert r.next_state == "coleta_orcamento_personalizacao"
    assert s.session_data["orcamento_quantidade"] == 50


# 12. CONFIRMACAO_ORCAMENTO
def test_confirmacao_confirmar(faq):
    s = make_session(
        "confirmacao_orcamento",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
            "orcamento_personalizacao": "Bordado",
            "orcamento_prazo": "15 dias",
        },
    )
    r = handle("confirmar", s, faq)
    assert r.action == "capture_lead"
    assert r.next_state == "lead_capturado"


def test_confirmacao_corrigir(faq):
    s = make_session(
        "confirmacao_orcamento",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
            "orcamento_personalizacao": "Bordado",
            "orcamento_prazo": "15 dias",
        },
    )
    r = handle("corrigir", s, faq)
    assert r.next_state == "coleta_orcamento_qtd"


# 13. Estado desconhecido → defensive reset
def test_unknown_state_resets_to_inicio(faq):
    s = make_session("estado_que_nao_existe", nome="Maria")
    r = handle("mensagem", s, faq)
    assert r.next_state == "inicio"


# ── Fluxo de orçamento ponta-a-ponta (cobertura extra) ────────────────────


def test_menu_trigger_orcamento_text(faq):
    s = make_session("menu", nome="Maria")
    r = handle("orçamento", s, faq)
    assert r.next_state == "coleta_orcamento_segmento"
    assert r.response.type == "list"


def test_segmento_valido_avanca_para_produto(faq):
    # [redesign-orcamento] segmento agora é armazenado como rótulo de
    # exibição ("Corporativo", não "corporativo").
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("corporativo", s, faq)
    assert r.next_state == "coleta_orcamento_produto"
    assert s.session_data["orcamento_segmento"] == "Corporativo"


def test_produto_valido_avanca_para_qtd(faq):
    s = make_session(
        "coleta_orcamento_produto",
        nome="Maria",
        data={"orcamento_segmento": "Corporativo"},
    )
    r = handle("Camisa Polo", s, faq)
    assert r.next_state == "coleta_orcamento_qtd"
    assert s.session_data["orcamento_produto"] == "Camisa Polo"


def test_produto_via_numeral(faq):
    # [redesign-orcamento] "4" → "Jaleco Tradicional".
    s = make_session(
        "coleta_orcamento_produto",
        nome="Maria",
        data={"orcamento_segmento": "Saúde"},
    )
    r = handle("4", s, faq)
    assert r.next_state == "coleta_orcamento_qtd"
    assert s.session_data["orcamento_produto"] == "Jaleco Tradicional"


def test_produto_texto_livre_aceito(faq):
    # [redesign-orcamento] Produto fora do catálogo é armazenado como veio,
    # sem rejeição. O consultor humano interpreta no resumo.
    s = make_session(
        "coleta_orcamento_produto",
        nome="Maria",
        data={"orcamento_segmento": "Educação"},
    )
    msg = "camiseta estampada com logo da escola"
    r = handle(msg, s, faq)
    assert r.next_state == "coleta_orcamento_qtd"
    # Match é exato — descrição rica vira free text, preservando detalhe
    assert s.session_data["orcamento_produto"] == msg


def test_produto_descricao_complexa_preservada(faq):
    # Múltiplos produtos numa frase — preserva texto livre completo.
    s = make_session(
        "coleta_orcamento_produto",
        nome="Maria",
        data={"orcamento_segmento": "Corporativo"},
    )
    msg = "uniforme com saia e camisa bordada"
    r = handle(msg, s, faq)
    assert r.next_state == "coleta_orcamento_qtd"
    assert s.session_data["orcamento_produto"] == msg


def test_personalizacao_valida_avanca_para_prazo(faq):
    s = make_session(
        "coleta_orcamento_personalizacao",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
        },
    )
    # [fix-Q3] bordado vai para coleta_bordado_info antes; serigrafia/sem
    # personalização vão direto para prazo. Usamos serigrafia aqui.
    r = handle("serigrafia", s, faq)
    assert r.next_state == "coleta_orcamento_prazo"
    assert s.session_data["orcamento_personalizacao"] == "serigrafia"


def test_prazo_valido_vai_para_confirmacao(faq):
    s = make_session(
        "coleta_orcamento_prazo",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
            "orcamento_personalizacao": "Bordado",
        },
    )
    r = handle("15 dias", s, faq)
    assert r.next_state == "confirmacao_orcamento"
    assert "Resumo" in r.response.body


def test_lead_capturado_menu(faq):
    s = make_session("lead_capturado", nome="Maria")
    r = handle("menu", s, faq)
    assert r.next_state == "menu"


def test_envia_catalogo_state_returns_to_menu(faq):
    s = make_session("envia_catalogo", nome="Maria")
    r = handle("qualquer coisa", s, faq)
    assert r.next_state == "menu"


# ── S04-07: Texto livre nos estados de orçamento ─────────────────────────


def test_segmento_saude_acentuado(faq):
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("Saúde", s, faq)
    assert r.next_state != "coleta_orcamento_segmento", \
        "Saúde com acento deve avançar o estado"
    assert s.session_data.get("orcamento_segmento") == "Saúde"


def test_segmento_corporativo_maiusculo(faq):
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    handle("Corporativo", s, faq)
    assert s.session_data.get("orcamento_segmento") == "Corporativo"


def test_segmento_por_numero(faq):
    # [redesign-orcamento] "1" → "Corporativo" (mapa numeral 1..6).
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("1", s, faq)
    assert r.next_state == "coleta_orcamento_produto"
    assert s.session_data.get("orcamento_segmento") == "Corporativo"


def test_segmento_educacao_via_alias(faq):
    # [redesign-orcamento] "escolar"/"escola" → "Educação" via alias.
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("escolar", s, faq)
    assert r.next_state == "coleta_orcamento_produto"
    assert s.session_data.get("orcamento_segmento") == "Educação"


def test_segmento_desconhecido_aceita_como_outro(faq):
    # [redesign-orcamento] Antes a entrada desconhecida ficava presa em
    # COLETA_ORCAMENTO_SEGMENTO. Agora vira "Outro (texto)" e avança —
    # o consultor humano vê o que o cliente escreveu.
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("pet shop", s, faq)
    assert r.next_state == "coleta_orcamento_produto"
    assert s.session_data.get("orcamento_segmento") == "Outro (pet shop)"


def test_segmento_saude_avanca_para_produto(faq):
    """[redesign-orcamento] Saúde sempre vai para COLETA_ORCAMENTO_PRODUTO
    (com lista completa de 8 produtos), nunca pula para QTD."""
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("saude", s, faq)
    assert r.next_state == "coleta_orcamento_produto"
    assert s.session_data.get("orcamento_segmento") == "Saúde"


def test_personalizacao_bordado_livre(faq):
    s = make_session(
        "coleta_orcamento_personalizacao",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
        },
    )
    r = handle("Bordado", s, faq)
    # [fix-Q3] bordado agora vai para coleta_bordado_info antes do prazo
    assert r.next_state == "coleta_bordado_info"
    assert s.session_data.get("orcamento_personalizacao") == "bordado"


def test_personalizacao_sem_personalizacao(faq):
    s = make_session(
        "coleta_orcamento_personalizacao",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
        },
    )
    r = handle("sem personalização", s, faq)
    assert r.next_state == "coleta_orcamento_prazo"


def test_confirmacao_sim_captura_lead(faq):
    s = make_session(
        "confirmacao_orcamento",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
            "orcamento_personalizacao": "bordado",
            "orcamento_prazo": "15 dias",
        },
    )
    r = handle("sim", s, faq)
    assert r.action == "capture_lead"


def test_confirmacao_ok_captura_lead(faq):
    s = make_session(
        "confirmacao_orcamento",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
            "orcamento_personalizacao": "bordado",
            "orcamento_prazo": "15 dias",
        },
    )
    r = handle("ok", s, faq)
    assert r.action == "capture_lead"


def test_confirmacao_nao_volta_qtd(faq):
    s = make_session(
        "confirmacao_orcamento",
        nome="Maria",
        data={
            "orcamento_segmento": "corporativo",
            "orcamento_produto": "Camisa Polo",
            "orcamento_quantidade": 50,
            "orcamento_personalizacao": "bordado",
            "orcamento_prazo": "15 dias",
        },
    )
    r = handle("não", s, faq)
    assert r.next_state == "coleta_orcamento_qtd"


def test_falar_humano_texto_livre_no_menu(faq):
    s = make_session("menu", nome="Maria")
    r = handle("falar com atendente", s, faq)
    assert r.next_state != "menu" or r.action == "forward_to_human"
