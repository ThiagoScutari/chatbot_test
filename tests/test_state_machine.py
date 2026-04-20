"""Testes da lógica do state_machine.handle()."""
from pathlib import Path

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


@pytest.fixture
def faq_engine():
    return FAQEngine(Path("app/knowledge/faq.json"))


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


def test_menu_alias_numerico_1_vai_para_aguarda_pedido(faq_engine, campaign_engine):
    """Canais que renderizam botões como lista numerada (Telegram)
    devem conseguir rotear '1' para consultar_pedido."""
    r = handle("1", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == AGUARDA_PEDIDO


def test_menu_alias_numerico_2_dispara_catalogo(faq_engine, campaign_engine):
    r = handle("2", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == ENVIA_CATALOGO
    assert r.action == "send_catalog"


def test_menu_alias_numerico_3_encaminha_humano(faq_engine, campaign_engine):
    r = handle("3", _sess(MENU), faq_engine, campaign_engine)
    assert r.next_state == ENCAMINHAR_HUMANO
    assert r.action == "forward_to_human"


def test_menu_button_id_original_continua_funcionando(faq_engine, campaign_engine):
    """Compatibilidade com WhatsApp Interactive: button ids ainda funcionam."""
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
