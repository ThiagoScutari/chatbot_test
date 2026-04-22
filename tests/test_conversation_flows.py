"""Testes de fluxo conversacional — automatização dos 20 cenários
do dogfooding manual (docs/dogfood/).

Cada teste corresponde a um cenário do checklist:
C01-C20. Ao passar aqui, o cenário está aprovado.

C03 é intencionalmente manual (timeout real de 2h) e não está aqui.
"""
from __future__ import annotations

import pytest

from tests.helpers.conversation_simulator import ConversationSimulator


pytestmark = pytest.mark.asyncio


# ── BLOCO 1: Onboarding ──────────────────────────────────────────────────────

async def test_C01_start_pede_nome(sim):
    """C01: /start → boas-vindas + pede nome, NÃO mostra menu."""
    await sim.send("/start")
    assert sim.state == "aguarda_nome"
    assert any(
        w in sim.last_response.lower()
        for w in ["bem-vind", "assistente", "camisart", "nome"]
    )
    assert "1." not in sim.last_response


async def test_C02_nome_salvo_e_menu_apresentado(sim):
    """C02: Enviar nome → salvo na sessão + menu apresentado."""
    await sim.send("/start")
    await sim.send("Thiago")
    assert sim.nome_cliente == "Thiago"
    assert sim.state == "menu"
    assert sim.last_text_contains("ajud") or sim.last_buttons


async def test_C04_start_novamente_com_sessao_ativa(sim):
    """C04: /start com sessão ativa → boas-vindas, não fallback."""
    await sim.send("/start")
    await sim.send("Maria")
    await sim.send("/start")
    assert sim.state == "aguarda_nome"
    response = sim.last_response.lower()
    assert "não entendi" not in response
    assert "como posso" not in response or "bem-vind" in response


# ── BLOCO 2: FAQ ─────────────────────────────────────────────────────────────

async def test_C05_preco_polo(sim):
    """C05: Pergunta de preço da polo → resposta com valor."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço da polo?")
    assert any(
        w in sim.last_response for w in ["45", "42", "R$", "polo"]
    )


async def test_C06_preco_polo_erro_ortografico(sim):
    """C06: Camiza Polu (erro duplo) → mesmo resultado."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("Camiza Polu")
    assert any(
        w in sim.last_response
        for w in ["45", "42", "R$", "polo", "Polo"]
    )


async def test_C07_endereco(sim):
    """C07: Onde fica → endereço completo."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("onde fica a loja?")
    assert (
        "Magalhães Barata" in sim.last_response
        or "445" in sim.last_response
    )


async def test_C08_pedido_minimo(sim):
    """C08: Pedido mínimo → resposta correta."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("tem pedido mínimo?")
    assert sim.last_response
    assert (
        "mínimo" in sim.last_response.lower()
        or "peça" in sim.last_response.lower()
    )


async def test_C09_prazo_bordado(sim):
    """C09: Prazo do bordado → 5 dias úteis."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("quanto demora o bordado?")
    assert (
        "5" in sim.last_response
        or "dias" in sim.last_response.lower()
    )


async def test_C10_entrega_nacional_estado(sim):
    """C10: Entrega em SP → confirma entrega nacional."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("entregam para São Paulo?")
    assert sim.last_response
    assert any(
        w in sim.last_response.lower()
        for w in ["brasil", "estado", "entreg", "correio"]
    )


async def test_C10b_entrega_sigla_estado(sim):
    """C10b: Entrega em SC (sigla) → confirma entrega nacional."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("entrega em SC?")
    assert sim.last_response
    assert any(
        w in sim.last_response.lower()
        for w in ["brasil", "estado", "entreg"]
    )


# ── BLOCO 3: Fluxo de orçamento ──────────────────────────────────────────────

async def test_C11_catalogo_entregue(sim):
    """C11: ver_catalogo → lista de produtos entregue."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("ver_catalogo")
    all_responses = " ".join(sim.history())
    assert any(
        produto in all_responses
        for produto in [
            "Polo",
            "Jaleco",
            "Básica",
            "Regata",
            "Camisart",
        ]
    )


async def test_C12_fluxo_orcamento_completo(sim):
    """C12: Fluxo completo segmento→produto→qtd→personalização→prazo→confirmar."""
    await sim.send("/start")
    await sim.send("Thiago")

    # Iniciar orçamento
    await sim.send("quero fazer um orçamento")
    assert "coleta_orcamento" in sim.state or sim.state == "menu"

    if sim.state == "menu":
        await sim.send("3")

    # Segmento
    await sim.send("Corporativo")
    assert (
        "produto" in sim.last_response.lower()
        or "peça" in sim.last_response.lower()
    )

    # Produto
    await sim.send("Camisa Polo")

    # Quantidade
    await sim.send("50")
    assert sim.state == "coleta_orcamento_personalizacao"
    assert sim.session_data.get("orcamento_quantidade") == 50

    # Personalização
    await sim.send("Bordado")
    assert sim.state == "coleta_orcamento_prazo"

    # Prazo
    await sim.send("15 dias")
    assert sim.state == "confirmacao_orcamento"
    assert "50" in sim.last_response

    # Confirmar
    await sim.send("sim")
    assert sim.state == "lead_capturado"

    # Verificar lead no banco
    leads = sim.leads_captured()
    assert len(leads) == 1
    lead = leads[0]
    assert lead.status == "novo"
    assert lead.quantidade == 50
    assert lead.segmento == "corporativo"
    assert lead.personalizacao == "bordado"


async def test_C13_quantidade_invalida_repergunta(sim):
    """C13: 'muitas' na quantidade → repergunta sem avançar estado."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("quero orçamento")
    await sim.send("Corporativo")
    await sim.send("Camisa Polo")

    await sim.send("muitas")
    assert sim.state == "coleta_orcamento_qtd"
    assert sim.session_data.get("orcamento_quantidade") is None


async def test_C14_corrigir_volta_para_quantidade(sim):
    """C14: 'corrigir' na confirmação → volta para quantidade."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("quero orçamento")
    await sim.send("Corporativo")
    await sim.send("Camisa Polo")
    await sim.send("50")
    await sim.send("Bordado")
    await sim.send("15 dias")
    assert sim.state == "confirmacao_orcamento"
    await sim.send("corrigir")
    assert sim.state == "coleta_orcamento_qtd"


async def test_C15_lead_gravado_no_banco(sim, db):
    """C15: Orçamento confirmado → lead no banco com dados corretos."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("quero orçamento")
    await sim.send("Saúde")
    await sim.send("Jaleco Tradicional")
    await sim.send("10")
    await sim.send("Bordado")
    await sim.send("urgente")
    await sim.send("sim")

    leads = sim.leads_captured()
    assert leads, "Nenhum lead foi capturado"
    lead = leads[0]
    assert lead.status == "novo"
    assert lead.nome_cliente == "Thiago"
    assert lead.segmento == "saude"
    assert lead.quantidade == 10
    assert lead.prazo_desejado == "urgente"


async def test_C16_segmento_saude_mostra_jaleco(sim):
    """C16: Segmento saúde → lista apenas jalecos."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("quero orçamento")
    await sim.send("Saúde")
    response = sim.last_response.lower()
    all_text = " ".join(sim.history()).lower()
    assert "jaleco" in all_text
    assert "polo" not in response


# ── BLOCO 4: Handoff ─────────────────────────────────────────────────────────

async def test_C17_falar_humano_handoff(sim):
    """C17: 'falar com atendente' → mensagem de handoff."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("falar com atendente")
    assert sim.state in ("encaminhar_humano", "aguarda_retorno_humano")
    assert any(
        w in sim.last_response.lower()
        for w in ["consultor", "atendente", "equipe", "horário"]
    )


async def test_C18_aguarda_retorno_nao_trava(sim):
    """C18: Mensagem após handoff → responde, não trava em loop."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("falar com atendente")

    await sim.send("oi, ainda estou aqui")
    assert sim.state == "aguarda_retorno_humano"
    assert sim.last_response


# ── BLOCO 5: Edge cases ──────────────────────────────────────────────────────

async def test_C19_rate_limit_11a_mensagem(pipeline, db):
    """C19: 11 mensagens em 1 min → 11ª bloqueada (retorna None)."""
    sim = ConversationSimulator(pipeline, db, user_id="TEST_RL_C19")
    await sim.send("/start")
    await sim.send("Thiago")

    blocked = False
    for i in range(9):
        result = await sim.send(f"mensagem {i}")
        if result is None:
            blocked = True
            break

    assert blocked, "Rate limit não bloqueou após 10 mensagens"


async def test_C20_fora_do_escopo_retorna_fallback(sim):
    """C20: Pergunta fora do escopo → fallback com menu, sem crash."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço do bitcoin?")
    assert sim.last_response
    assert sim.state == "menu"
