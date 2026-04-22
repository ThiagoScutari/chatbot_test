from pathlib import Path

import pytest

from app.engines.regex_engine import FAQEngine


FAQ_PATH = Path("app/knowledge/faq.json")


@pytest.fixture(scope="module")
def engine():
    return FAQEngine(FAQ_PATH)


def test_real_preco_polo(engine):
    assert engine.match("quanto custa a polo?") is not None


def test_real_plus_size(engine):
    assert engine.match("tem polo plus size?") is not None


def test_real_entrega_interior(engine):
    assert engine.match("faz entrega para o interior?") is not None


def test_real_aceita_cartao(engine):
    assert engine.match("aceita cartão?") is not None


def test_real_manga_longa(engine):
    assert engine.match("tem camisa manga longa?") is not None


def test_real_tamanho_maior(engine):
    assert engine.match("qual o tamanho maior que tem?") is not None


def test_real_personalizacao_foto(engine):
    assert engine.match("faz personalização com foto?") is not None


def test_real_camisa_feminina(engine):
    assert engine.match("tem camisa feminina?") is not None


def test_real_prazo_100_pecas(engine):
    assert engine.match("qual o prazo para 100 peças?") is not None


def test_real_restaurante(engine):
    assert engine.match("faz uniforme para restaurante?") is not None


def test_real_jaleco_feminino(engine):
    assert engine.match("tem jaleco feminino?") is not None


def test_real_time_futebol(engine):
    assert engine.match("faz camiseta para time de futebol?") is not None


def test_real_whatsapp(engine):
    assert engine.match("qual o Whatsapp de vocês?") is not None


def test_real_loja_fisica(engine):
    assert engine.match("tem loja física?") is not None


def test_real_pix(engine):
    assert engine.match("aceita pix?") is not None


def test_real_desconto_quantidade(engine):
    assert engine.match("tem desconto para quantidade?") is not None


def test_real_infantil(engine):
    assert engine.match("faz camisa polo infantil?") is not None


def test_real_dry_fit(engine):
    assert engine.match("tem tecido dry fit?") is not None


def test_real_instagram(engine):
    assert engine.match("qual o instagram de vocês?") is not None


def test_real_estoque_pronto(engine):
    assert engine.match("tem estoque pronto?") is not None
