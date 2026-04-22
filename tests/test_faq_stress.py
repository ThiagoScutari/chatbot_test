"""Stress tests do FAQEngine com variações linguísticas extensivas.

Cada intenção é testada com 8-15 variações diferentes — erros
ortográficos, gírias, abreviações, ordem invertida, frases longas.

Objetivo: cobertura linguística real, não apenas as 20 perguntas
do faq_coverage_check.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.engines.regex_engine import FAQEngine


@pytest.fixture(scope="module")
def faq():
    return FAQEngine(Path("app/knowledge/faq.json"))


# ── Preço Polo ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "qual o preço da polo?",
        "quanto custa a polo piquet?",
        "me fala o valor da polo",
        "polo quanto tá?",
        "preço polo piquê",
        "qual o valor da camisa polo?",
        "quanto fica a polo?",
        "polo piquet valor",
        "camiza polo quanto custa",
        "camisa polu preço",
        "quero saber o preço da polo",
        "tem polo? qual o valor?",
    ],
)
def test_preco_polo_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "preco_polo", (
        f"'{msg}' deveria casar preco_polo, casou: "
        f"{m.intent_id if m else None}"
    )


# ── Preço Jaleco ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "quanto custa o jaleco?",
        "preço do jaleco",
        "jaleco valor",
        "qual o preço do jaleco médico?",
        "jaleco de saúde quanto custa?",
        "me passa o preço do jaleco",
        "tem jaleco? qual o valor",
        "jalecos preço",
    ],
)
def test_preco_jaleco_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "preco_jaleco", (
        f"'{msg}' deveria casar preco_jaleco"
    )


# ── Endereço ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "onde fica a loja?",
        "qual o endereço?",
        "onde vocês ficam?",
        "localização da loja",
        "como chegar na Camisart?",
        "endereço da camisart belém",
        "onde é a loja física?",
        "me manda o endereço",
        "qual a localização de vocês?",
        "fica onde em belém?",
    ],
)
def test_endereco_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "endereco", (
        f"'{msg}' deveria casar endereco"
    )


# ── Prazo de Entrega ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "qual o prazo de entrega?",
        "quanto tempo demora?",
        "em quantos dias fica pronto?",
        "prazo pra entregar",
        "demora muito?",
        "quando fica pronto?",
        "é rápido?",
        "entrega urgente tem?",
        "preciso pra semana que vem",
        "qual o tempo de produção?",
    ],
)
def test_prazo_entrega_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar algum intent de prazo"


# ── Bordado ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "qual o prazo do bordado?",
        "quanto tempo leva o bordado?",
        "fazem bordado?",
        "bordado de logo",
        "quero bordado na camisa",
        "tem bordado?",
        "bordado demora quanto?",
        "prazo pra bordar",
        "bordado personalizado",
        "colocar logo bordada",
    ],
)
def test_bordado_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar intent de bordado"


# ── Pedido Mínimo ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "tem pedido mínimo?",
        "pedido minimo",
        "qual o mínimo?",
        "posso comprar só 1 peça?",
        "compro avulso?",
        "mínimo de peças",
        "dá pra comprar 1 só?",
        "tem quantidade mínima?",
        "preciso comprar quantas peças no mínimo?",
    ],
)
def test_pedido_minimo_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar pedido_minimo"


# ── Entrega Nacional ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "entregam para fora de Belém?",
        "entrega pra São Paulo?",
        "vocês entregam pro Brasil todo?",
        "frete pra SC",
        "entrega em SP",
        "mando buscar ou vocês entregam?",
        "entrega para o interior do Pará?",
        "faz envio nacional?",
        "posso receber em outro estado?",
        "entrega pra RJ?",
        "manda pelo correios?",
        "fora do Pará entrega?",
    ],
)
def test_entrega_nacional_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar entrega_nacional"


# ── Falar Humano ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "falar com atendente",
        "quero falar com uma pessoa",
        "preciso de um vendedor",
        "me passa pra um humano",
        "atendente por favor",
        "tem alguém pra me atender?",
        "quero falar com o responsável",
        "me conecta com um consultor",
        "não quero falar com robô",
        "transfere pra um humano",
    ],
)
def test_falar_humano_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "falar_humano", (
        f"'{msg}' deveria casar falar_humano"
    )


# ── Pagamento ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "aceita pix?",
        "aceita cartão?",
        "como pago?",
        "formas de pagamento",
        "aceita boleto?",
        "pago com pix?",
        "tem parcelamento?",
        "aceita débito?",
        "pagamento à vista tem desconto?",
    ],
)
def test_pagamento_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar intent de pagamento"


# ── Feminino ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "tem camisa feminina?",
        "tem polo feminina?",
        "linha feminina",
        "tem baby look?",
        "camisa pra mulher",
        "polo feminina tem?",
        "jaleco feminino?",
    ],
)
def test_feminino_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar intent feminino"


# ── Tamanhos ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "que tamanhos têm?",
        "tem GG?",
        "tamanhos disponíveis",
        "tem plus size?",
        "qual o maior tamanho?",
        "tem G2 G3?",
        "tamanho extra grande",
        "tem tamanho especial?",
    ],
)
def test_tamanhos_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar intent de tamanho"


# ── Desconto / Atacado ───────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "tem desconto pra quantidade?",
        "preço de atacado?",
        "desconto pra 100 peças",
        "compro bastante tem desconto?",
        "tabela de atacado",
        "preço por lote",
        "quanto fica 50 peças?",
        "desconto pra empresa?",
    ],
)
def test_desconto_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar desconto_quantidade"


# ── /start e variações ───────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "/start",
        "/start@camisart_dev_bot",
        "/START",
    ],
)
def test_start_command_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "start_command", (
        f"'{msg}' deveria casar start_command"
    )


# ── Fallback esperado (NÃO deve casar nenhum intent) ─────────────────────────
@pytest.mark.parametrize(
    "msg",
    [
        "qual o preço do bitcoin?",
        "me conta uma piada",
        "como está o tempo em Belém?",
        "jogo do bicho",
        "receita de bolo",
    ],
)
def test_fora_do_escopo_retorna_none(faq, msg):
    m = faq.match(msg)
    assert m is None, (
        f"'{msg}' NÃO deveria casar nenhum intent, "
        f"casou: {m.intent_id if m else None}"
    )
