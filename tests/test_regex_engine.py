import json
from pathlib import Path

import pytest

from app.engines.regex_engine import FAQEngine


FAQ_PATH = Path("app/knowledge/faq.json")


@pytest.fixture
def engine():
    return FAQEngine(FAQ_PATH)


def test_preco_polo_match(engine):
    m = engine.match("qual o preço da polo?")
    assert m is not None
    assert m.intent_id == "preco_polo"


def test_preco_polo_variacao(engine):
    assert engine.match("quanto custa a polo piquet") is not None


def test_preco_polo_erro_ortografico(engine):
    assert engine.match("quanto custa a camiza polo") is not None


def test_jaleco_match(engine):
    m = engine.match("preço do jaleco")
    assert m is not None
    assert m.intent_id == "preco_jaleco"


def test_endereco_match(engine):
    m = engine.match("onde fica a loja?")
    assert m is not None
    assert m.intent_id == "endereco"


def test_bordado_match(engine):
    m = engine.match("qual o prazo do bordado?")
    assert m is not None


def test_pedido_minimo_match(engine):
    m = engine.match("tem pedido mínimo?")
    assert m is not None
    assert m.intent_id == "pedido_minimo"


def test_prazo_entrega_match(engine):
    m = engine.match("quanto tempo demora?")
    assert m is not None


def test_tamanhos_match(engine):
    assert engine.match("que tamanhos vocês têm?") is not None


def test_no_match_returns_none(engine):
    assert engine.match("xablau foobar inexistente") is None


def test_invalid_regex_does_not_crash(tmp_path):
    bad_faq = {
        "version": "1.0",
        "intents": [
            {
                "id": "bad",
                "priority": 1,
                "patterns": ["[invalid"],
                "response": {"type": "text", "body": "x"},
            }
        ],
        "fallback": {"response": {"type": "text", "body": "fallback"}},
    }
    p = tmp_path / "bad_faq.json"
    p.write_text(json.dumps(bad_faq))
    e = FAQEngine(p)
    assert e.match("anything") is None  # não levanta


def test_priority_higher_wins(tmp_path):
    faq = {
        "version": "1.0",
        "intents": [
            {
                "id": "low",
                "priority": 1,
                "patterns": ["\\bpolo\\b"],
                "response": {"type": "text", "body": "low"},
            },
            {
                "id": "high",
                "priority": 10,
                "patterns": ["\\bpolo\\b"],
                "response": {"type": "text", "body": "high"},
            },
        ],
        "fallback": {"response": {"type": "text", "body": "fb"}},
    }
    p = tmp_path / "prio.json"
    p.write_text(json.dumps(faq))
    e = FAQEngine(p)
    m = e.match("polo")
    assert m is not None
    assert m.intent_id == "high"


def test_fallback_is_buttons_with_three(engine):
    fb = engine.fallback_response()
    assert fb.type == "buttons"
    assert fb.buttons is not None
    assert len(fb.buttons) == 3


def test_start_command_match(engine):
    m = engine.match("/start")
    assert m is not None
    assert m.intent_id == "start_command"


def test_start_command_with_botname(engine):
    m = engine.match("/start@camisart_dev_bot")
    assert m is not None
    assert m.intent_id == "start_command"


def test_start_command_priority_over_others(engine):
    # /start must never fall to fallback
    m = engine.match("/start")
    assert m is not None
    assert m.follow_up_state == "aguarda_nome"


def test_falar_humano_atendente(engine):
    m = engine.match("falar com atendente")
    assert m is not None
    assert m.intent_id == "falar_humano"


def test_falar_humano_vendedor(engine):
    assert engine.match("preciso de um vendedor") is not None


def test_falar_humano_pessoa(engine):
    assert engine.match("quero falar com uma pessoa") is not None


def test_falar_humano_keyword_alone(engine):
    assert engine.match("atendente") is not None


def test_falar_humano_nao_entendi(engine):
    assert engine.match("não consigo entender") is not None


def test_entrega_sigla_estado(engine):
    assert engine.match("entrega em SC?") is not None


def test_entrega_nome_estado(engine):
    assert engine.match("entrega em São Paulo") is not None


def test_entrega_fora_belem(engine):
    assert engine.match("fora de Belém") is not None


def test_polo_camiza_polu(engine):
    assert engine.match("Camiza Polu") is not None


def test_polo_variacao_u(engine):
    assert engine.match("qual o preço da polu?") is not None
