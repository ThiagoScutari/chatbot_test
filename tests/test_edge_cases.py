"""Edge cases e inputs adversariais."""
from __future__ import annotations

import pytest

from tests.helpers.conversation_simulator import ConversationSimulator


pytestmark = pytest.mark.asyncio


async def test_mensagem_vazia(sim):
    """String vazia não deve crashar o bot."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("")
    assert sim.state in ("menu", "aguarda_nome")


async def test_mensagem_apenas_espacos(sim):
    """Espaços não devem crashar."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("   ")
    assert True


async def test_mensagem_muito_longa(sim):
    """Mensagem de 5000 chars não deve crashar."""
    await sim.send("/start")
    await sim.send("Thiago")
    texto_longo = "polo " * 1000
    await sim.send(texto_longo)
    assert True


async def test_emojis_nao_quebram_regex(sim):
    """Emojis em mensagens não devem quebrar o FAQEngine."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço da polo? 🤔")
    assert any(
        w in sim.last_response for w in ["45", "42", "polo", "Polo"]
    )


async def test_mensagem_so_numeros(sim):
    """Só números no menu → roteamento correto ou fallback."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("1")
    assert sim.state != "menu" or sim.last_response


async def test_injecao_sql_nao_quebra(sim):
    """Input com SQL injection não deve quebrar o banco."""
    await sim.send("/start")
    await sim.send("'; DROP TABLE sessions; --")
    assert True


async def test_nome_com_caracteres_especiais(sim):
    """Nome com acentos e caracteres especiais é salvo corretamente."""
    await sim.send("/start")
    await sim.send("José Antônio da Conceição")
    assert sim.nome_cliente == "José Antônio da Conceição"
    assert sim.state == "menu"


async def test_multiplos_orcamentos_mesma_sessao(sim, db):
    """Usuário pode fazer mais de um orçamento na mesma sessão."""
    await sim.send("/start")
    await sim.send("Maria")

    # Primeiro orçamento
    await sim.send("quero orçamento")
    await sim.send("Corporativo")
    await sim.send("Camisa Polo")
    await sim.send("30")
    await sim.send("Bordado")
    await sim.send("15 dias")
    await sim.send("sim")
    assert len(sim.leads_captured()) == 1

    # Segundo orçamento na mesma sessão
    await sim.send("quero outro orçamento")
    await sim.send("Saúde")
    await sim.send("Jaleco Tradicional")
    await sim.send("5")
    await sim.send("sem personalização")
    await sim.send("urgente")
    await sim.send("sim")
    assert len(sim.leads_captured()) == 2


async def test_faq_durante_orcamento(sim):
    """FAQ de alta prioridade responde mesmo durante fluxo de orçamento."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("quero orçamento")
    await sim.send("Corporativo")
    await sim.send("Camisa Polo")
    await sim.send("qual o endereço de vocês?")
    assert (
        "Magalhães" in sim.last_response
        or "445" in sim.last_response
    )


async def test_sessao_isolada_entre_usuarios(pipeline, db):
    """Dois usuários simultâneos não interferem um no outro."""
    sim_a = ConversationSimulator(pipeline, db, user_id="TEST_USER_A")
    sim_b = ConversationSimulator(pipeline, db, user_id="TEST_USER_B")

    await sim_a.send("/start")
    await sim_a.send("Alice")

    await sim_b.send("/start")
    await sim_b.send("Bob")

    assert sim_a.nome_cliente == "Alice"
    assert sim_b.nome_cliente == "Bob"
    assert sim_a.state == sim_b.state == "menu"
