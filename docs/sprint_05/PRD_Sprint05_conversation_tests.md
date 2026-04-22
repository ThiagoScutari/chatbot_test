# PRD — Sprint 05: Testes Conversacionais Automatizados
**Projeto:** Camisart AI  
**Branch:** `sprint/05-conversation-tests`  
**Status:** Aprovação Pendente  
**Origem:** Dogfooding manual Sprint 04 — necessidade de automação + bugs remanescentes  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Prioridade |
|---|---|---|---|
| S05-01 | `tests/` | `ConversationSimulator` — simula conversas completas sem Telegram | 🔴 |
| S05-02 | `tests/` | Testes de fluxo completo — 20 cenários do dogfooding automatizados | 🔴 |
| S05-03 | `tests/` | Stress tests de FAQ — 80+ variações de perguntas reais | 🔴 |
| S05-04 | `tests/` | Edge cases e inputs adversariais | 🟡 |
| S05-05 | `engines/` | Corrigir bugs remanescentes do dogfooding (C10, C17, C19, C20) | 🔴 |
| S05-06 | `docs/` | Atualizar `go_live_checklist.md` com critérios de testes automatizados | 🟡 |

---

## Objetivo do Sprint

**Nunca mais testar manualmente o que pode ser automatizado.**

Ao final deste sprint, `pytest tests/` valida todos os fluxos conversacionais do bot — onboarding, FAQ, orçamento completo, handoff, edge cases, stress de variações linguísticas. O CI detecta regressões antes que cheguem ao Telegram. O dogfooding manual vira validação de UX, não de funcionalidade.

---

## S05-01 — ConversationSimulator

### Design

O `ConversationSimulator` é um cliente de teste de alto nível que simula um usuário conversando com o bot através do `MessagePipeline` real — sem mocks de business logic, sem Telegram, sem HTTP.

```python
# tests/helpers/conversation_simulator.py

class ConversationSimulator:
    """
    Simula uma conversa completa através do MessagePipeline.

    Uso básico:
        sim = ConversationSimulator(pipeline, db)
        sim.send("/start")
        assert sim.last_text_contains("bem-vindo")
        sim.send("Thiago")
        assert sim.state == "menu"

    O simulador mantém a mesma sessão entre mensagens — exatamente
    como um usuário real conversando pelo Telegram.
    """

    def __init__(
        self,
        pipeline: MessagePipeline,
        db: Session,
        channel_id: str = "telegram",
        user_id: str | None = None,
    ):
        self.pipeline = pipeline
        self.db = db
        self.channel_id = channel_id
        self.user_id = user_id or f"TEST_SIM_{uuid.uuid4().hex[:8]}"
        self.message_counter = 0
        self._last_outbound: OutboundMessage | None = None
        self._sent_messages: list[OutboundMessage] = []

    async def send(self, text: str) -> OutboundMessage | None:
        """Envia uma mensagem e retorna o OutboundMessage de resposta."""
        self.message_counter += 1
        inbound = InboundMessage(
            channel_id=self.channel_id,
            channel_message_id=f"sim_{self.user_id}_{self.message_counter}",
            channel_user_id=self.user_id,
            display_name="TEST_Simulador",
            content=text,
            timestamp=datetime.now(timezone.utc),
            raw_payload={"simulated": True, "text": text},
        )
        outbound = await self.pipeline.process(inbound, self.db)
        self._last_outbound = outbound
        if outbound:
            self._sent_messages.append(outbound)
        return outbound

    @property
    def last_response(self) -> str:
        """Corpo da última resposta do bot."""
        if not self._last_outbound:
            return ""
        return self._last_outbound.response.get("body", "")

    @property
    def last_response_type(self) -> str:
        """Tipo da última resposta: text, buttons, list."""
        if not self._last_outbound:
            return ""
        return self._last_outbound.response.get("type", "text")

    @property
    def last_buttons(self) -> list[dict]:
        """Botões da última resposta (se tipo == buttons)."""
        if not self._last_outbound:
            return []
        return self._last_outbound.response.get("buttons", [])

    @property
    def state(self) -> str:
        """Estado atual da sessão no banco."""
        from app.models.session import Session as SessionModel
        session = self.db.query(SessionModel).filter_by(
            channel_id=self.channel_id,
            channel_user_id=self.user_id,
        ).first()
        return session.current_state if session else "unknown"

    @property
    def session_data(self) -> dict:
        """session_data atual da sessão."""
        from app.models.session import Session as SessionModel
        session = self.db.query(SessionModel).filter_by(
            channel_id=self.channel_id,
            channel_user_id=self.user_id,
        ).first()
        return session.session_data if session else {}

    @property
    def nome_cliente(self) -> str | None:
        """nome_cliente atual da sessão."""
        from app.models.session import Session as SessionModel
        session = self.db.query(SessionModel).filter_by(
            channel_id=self.channel_id,
            channel_user_id=self.user_id,
        ).first()
        return session.nome_cliente if session else None

    def last_text_contains(self, substring: str) -> bool:
        """Case-insensitive substring check na última resposta."""
        return substring.lower() in self.last_response.lower()

    def history(self) -> list[str]:
        """Lista de textos de todas as respostas do bot nesta conversa."""
        return [m.response.get("body", "") for m in self._sent_messages]

    def leads_captured(self) -> list:
        """Leads capturados por este simulador no banco."""
        from app.models.lead import Lead
        from app.models.session import Session as SessionModel
        session = self.db.query(SessionModel).filter_by(
            channel_id=self.channel_id,
            channel_user_id=self.user_id,
        ).first()
        if not session:
            return []
        return self.db.query(Lead).filter_by(session_id=session.id).all()
```

### Fixture no conftest.py

```python
# tests/conftest.py — adicionar

@pytest.fixture
def pipeline(db):
    """MessagePipeline com FAQEngine e CampaignEngine reais para testes."""
    from app.engines.campaign_engine import CampaignEngine
    from app.engines.regex_engine import FAQEngine
    from app.pipeline.message_pipeline import MessagePipeline
    from app.config import settings

    campaign = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign.reload()
    faq = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign)
    return MessagePipeline(faq_engine=faq, campaign_engine=campaign)

@pytest.fixture
def sim(pipeline, db):
    """ConversationSimulator pronto para uso."""
    from tests.helpers.conversation_simulator import ConversationSimulator
    return ConversationSimulator(pipeline, db)
```

---

## S05-02 — 20 cenários do dogfooding como testes pytest

```python
# tests/test_conversation_flows.py

"""
Testes de fluxo conversacional — automatização dos 20 cenários
do dogfooding manual (docs/dogfood/).

Cada teste corresponde a um cenário do checklist:
C01-C20. Ao passar aqui, o cenário está aprovado.
"""

import pytest
from tests.helpers.conversation_simulator import ConversationSimulator

pytestmark = pytest.mark.asyncio


# ── BLOCO 1: Onboarding ──────────────────────────────────────────────────────

async def test_C01_start_pede_nome(sim):
    """C01: /start → boas-vindas + pede nome, NÃO mostra menu."""
    await sim.send("/start")
    assert sim.state == "aguarda_nome"
    assert any(w in sim.last_response.lower()
               for w in ["bem-vind", "assistente", "camisart", "nome"])
    assert "1." not in sim.last_response  # não deve mostrar menu numerado

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
    # Segunda vez
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
    assert any(w in sim.last_response for w in ["45", "42", "R$", "polo"])

async def test_C06_preco_polo_erro_ortografico(sim):
    """C06: Camiza Polu (erro duplo) → mesmo resultado."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("Camiza Polu")
    assert any(w in sim.last_response for w in ["45", "42", "R$", "polo", "Polo"])

async def test_C07_endereco(sim):
    """C07: Onde fica → endereço completo."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("onde fica a loja?")
    assert "Magalhães Barata" in sim.last_response or "445" in sim.last_response

async def test_C08_pedido_minimo(sim):
    """C08: Pedido mínimo → resposta correta."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("tem pedido mínimo?")
    assert sim.last_response  # não é fallback vazio
    assert "mínimo" in sim.last_response.lower() or "peça" in sim.last_response.lower()

async def test_C09_prazo_bordado(sim):
    """C09: Prazo do bordado → 5 dias úteis."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("quanto demora o bordado?")
    assert "5" in sim.last_response or "dias" in sim.last_response.lower()

async def test_C10_entrega_nacional_estado(sim):
    """C10: Entrega em SP → confirma entrega nacional."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("entregam para São Paulo?")
    assert sim.last_response
    assert any(w in sim.last_response.lower()
               for w in ["brasil", "estado", "entreg", "correio"])

async def test_C10b_entrega_sigla_estado(sim):
    """C10b: Entrega em SC (sigla) → confirma entrega nacional."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("entrega em SC?")
    assert sim.last_response
    assert any(w in sim.last_response.lower()
               for w in ["brasil", "estado", "entreg"])


# ── BLOCO 3: Fluxo de orçamento ───────────────────────────────────────────────

async def test_C11_catalogo_entregue(sim):
    """C11: ver_catalogo → lista de produtos entregue."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("ver_catalogo")
    # Catálogo pode ter sido enviado como ação separada
    # Verificar histórico completo
    all_responses = " ".join(sim.history())
    assert any(produto in all_responses
               for produto in ["Polo", "Jaleco", "Básica", "Regata", "Camisart"])

async def test_C12_fluxo_orcamento_completo(sim):
    """C12: Fluxo completo segmento→produto→qtd→personalização→prazo→confirmar."""
    await sim.send("/start")
    await sim.send("Thiago")

    # Iniciar orçamento
    await sim.send("quero fazer um orçamento")
    assert "coleta_orcamento" in sim.state or sim.state == "menu"

    if sim.state == "menu":
        await sim.send("3")  # opção de orçamento

    # Segmento
    await sim.send("Corporativo")
    assert "produto" in sim.last_response.lower() or "peça" in sim.last_response.lower()

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
    assert "50" in sim.last_response  # resumo deve conter a quantidade

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

    state_antes = sim.state
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
    # Na confirmação
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
    assert "polo" not in response  # polo não deve aparecer para saúde


# ── BLOCO 4: Handoff ─────────────────────────────────────────────────────────

async def test_C17_falar_humano_handoff(sim):
    """C17: 'falar com atendente' → mensagem de handoff."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("falar com atendente")
    assert sim.state in ("encaminhar_humano", "aguarda_retorno_humano")
    assert any(w in sim.last_response.lower()
               for w in ["consultor", "atendente", "equipe", "horário"])

async def test_C18_aguarda_retorno_nao_trava(sim):
    """C18: Mensagem após handoff → responde, não trava em loop."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("falar com atendente")
    state_handoff = sim.state

    await sim.send("oi, ainda estou aqui")
    assert sim.state == "aguarda_retorno_humano"  # permanece
    assert sim.last_response  # respondeu algo


# ── BLOCO 5: Edge cases ───────────────────────────────────────────────────────

async def test_C19_rate_limit_11a_mensagem(pipeline, db):
    """C19: 11 mensagens em 1 min → 11ª bloqueada (retorna None)."""
    from tests.helpers.conversation_simulator import ConversationSimulator
    sim = ConversationSimulator(pipeline, db, user_id="TEST_RL_C19")
    await sim.send("/start")
    await sim.send("Thiago")

    # 9 mensagens adicionais (total 11 incluindo /start e nome)
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
    assert sim.last_response  # respondeu algo — não crashou
    assert sim.state == "menu"  # voltou ao menu
```

---

## S05-03 — Stress tests de FAQ (80+ variações)

```python
# tests/test_faq_stress.py

"""
Stress tests do FAQEngine com variações linguísticas extensivas.
Cada intenção é testada com 8-15 variações diferentes — erros
ortográficos, gírias, abreviações, ordem invertida, frases longas.

Objetivo: cobertura linguística real, não apenas as 20 perguntas
do faq_coverage_check.py.
"""

import pytest
from pathlib import Path
from app.engines.regex_engine import FAQEngine

@pytest.fixture(scope="module")
def faq():
    return FAQEngine(Path("app/knowledge/faq.json"))


# ── Preço Polo ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
    "qual o preço da polo?",
    "quanto custa a polo piquet?",
    "me fala o valor da polo",
    "polo quanto tá?",
    "preço polo piquê",
    "qual o valor da camisa polo?",
    "quanto fica a polo?",
    "polo piquet valor",
    "camiza polo quanto custa",   # erro ortográfico
    "camisa polu preço",          # erro ortográfico
    "quero saber o preço da polo",
    "tem polo? qual o valor?",
])
def test_preco_polo_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "preco_polo", \
        f"'{msg}' deveria casar preco_polo, casou: {m.intent_id if m else None}"


# ── Preço Jaleco ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
    "quanto custa o jaleco?",
    "preço do jaleco",
    "jaleco valor",
    "qual o preço do jaleco médico?",
    "jaleco de saúde quanto custa?",
    "me passa o preço do jaleco",
    "tem jaleco? qual o valor",
    "jalecos preço",
])
def test_preco_jaleco_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "preco_jaleco", \
        f"'{msg}' deveria casar preco_jaleco"


# ── Endereço ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
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
])
def test_endereco_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "endereco", \
        f"'{msg}' deveria casar endereco"


# ── Prazo de Entrega ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
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
])
def test_prazo_entrega_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar algum intent de prazo"


# ── Bordado ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
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
])
def test_bordado_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar intent de bordado"


# ── Pedido Mínimo ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
    "tem pedido mínimo?",
    "pedido minimo",
    "qual o mínimo?",
    "posso comprar só 1 peça?",
    "compro avulso?",
    "mínimo de peças",
    "dá pra comprar 1 só?",
    "tem quantidade mínima?",
    "preciso comprar quantas peças no mínimo?",
])
def test_pedido_minimo_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar pedido_minimo"


# ── Entrega Nacional ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
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
])
def test_entrega_nacional_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar entrega_nacional"


# ── Falar Humano ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
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
])
def test_falar_humano_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "falar_humano", \
        f"'{msg}' deveria casar falar_humano"


# ── Pagamento ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
    "aceita pix?",
    "aceita cartão?",
    "como pago?",
    "formas de pagamento",
    "aceita boleto?",
    "pago com pix?",
    "tem parcelamento?",
    "aceita débito?",
    "pagamento à vista tem desconto?",
])
def test_pagamento_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar intent de pagamento"


# ── Feminino ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
    "tem camisa feminina?",
    "tem polo feminina?",
    "linha feminina",
    "tem baby look?",
    "camisa pra mulher",
    "polo feminina tem?",
    "jaleco feminino?",
])
def test_feminino_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar intent feminino"


# ── Tamanhos ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
    "que tamanhos têm?",
    "tem GG?",
    "tamanhos disponíveis",
    "tem plus size?",
    "qual o maior tamanho?",
    "tem G2 G3?",
    "tamanho extra grande",
    "tem tamanho especial?",
])
def test_tamanhos_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar intent de tamanho"


# ── Desconto / Atacado ───────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
    "tem desconto pra quantidade?",
    "preço de atacado?",
    "desconto pra 100 peças",
    "compro bastante tem desconto?",
    "tabela de atacado",
    "preço por lote",
    "quanto fica 50 peças?",
    "desconto pra empresa?",
])
def test_desconto_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None, f"'{msg}' deveria casar desconto_quantidade"


# ── /start e variações ───────────────────────────────────────────────────────
@pytest.mark.parametrize("msg", [
    "/start",
    "/start@camisart_dev_bot",
    "/START",
])
def test_start_command_variacoes(faq, msg):
    m = faq.match(msg)
    assert m is not None and m.intent_id == "start_command", \
        f"'{msg}' deveria casar start_command"


# ── Fallback esperado (NÃO deve casar nenhum intent) ────────────────────────
@pytest.mark.parametrize("msg", [
    "qual o preço do bitcoin?",
    "me conta uma piada",
    "como está o tempo em Belém?",
    "jogo do bicho",
    "receita de bolo",
])
def test_fora_do_escopo_retorna_none(faq, msg):
    m = faq.match(msg)
    assert m is None, \
        f"'{msg}' NÃO deveria casar nenhum intent, casou: {m.intent_id if m else None}"
```

---

## S05-04 — Edge cases e inputs adversariais

```python
# tests/test_edge_cases.py

import pytest
pytestmark = pytest.mark.asyncio


async def test_mensagem_vazia(sim):
    """String vazia não deve crashar o bot."""
    await sim.send("/start")
    await sim.send("Thiago")
    result = await sim.send("")
    # Pode retornar None ou resposta de fallback — não deve crashar
    assert sim.state in ("menu", "aguarda_nome")


async def test_mensagem_apenas_espacos(sim):
    """Espaços não devem crashar."""
    await sim.send("/start")
    await sim.send("Thiago")
    result = await sim.send("   ")
    assert True  # não levantou exceção


async def test_mensagem_muito_longa(sim):
    """Mensagem de 5000 chars não deve crashar."""
    await sim.send("/start")
    await sim.send("Thiago")
    texto_longo = "polo " * 1000
    result = await sim.send(texto_longo)
    assert True  # não levantou exceção


async def test_emojis_nao_quebram_regex(sim):
    """Emojis em mensagens não devem quebrar o FAQEngine."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço da polo? 🤔")
    assert any(w in sim.last_response for w in ["45", "42", "polo", "Polo"])


async def test_mensagem_so_numeros(sim):
    """Só números no menu → roteamento correto ou fallback."""
    await sim.send("/start")
    await sim.send("Thiago")
    # No menu, "1" deve abrir consulta de pedido
    await sim.send("1")
    assert sim.state != "menu" or sim.last_response


async def test_injecao_sql_nao_quebra(sim):
    """Input com SQL injection não deve quebrar o banco."""
    await sim.send("/start")
    await sim.send("'; DROP TABLE sessions; --")
    assert True  # não levantou exceção


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

    # Volta ao menu e faz segundo orçamento
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
    # No meio do orçamento, pergunta sobre endereço
    estado_antes = sim.state
    await sim.send("qual o endereço de vocês?")
    assert "Magalhães" in sim.last_response or "445" in sim.last_response


async def test_sessao_isolada_entre_usuarios(pipeline, db):
    """Dois usuários simultâneos não interferem um no outro."""
    from tests.helpers.conversation_simulator import ConversationSimulator
    sim_a = ConversationSimulator(pipeline, db, user_id="TEST_USER_A")
    sim_b = ConversationSimulator(pipeline, db, user_id="TEST_USER_B")

    await sim_a.send("/start")
    await sim_a.send("Alice")

    await sim_b.send("/start")
    await sim_b.send("Bob")

    assert sim_a.nome_cliente == "Alice"
    assert sim_b.nome_cliente == "Bob"
    assert sim_a.state == sim_b.state == "menu"
```

---

## S05-05 — Corrigir bugs remanescentes do dogfooding

### C10 — "entregam para São Paulo?" ainda falhando

O pattern atual cobre `"São Paulo"` mas a mensagem exata do teste é `"entregam para São Paulo?"`. Adicionar variação:

```json
"\\bentregam\\b.*\\b(s[aã]o paulo|brasil|estado)\\b"
```

### C17 — "falar com atendente" ainda falhando após S04-02

Investigar se o intent `falar_humano` está sendo sobreposto por outro intent de maior prioridade, ou se o follow_up_state `encaminhar_humano` está sendo processado corretamente pela state machine.

Diagnóstico via test:
```python
def test_falar_humano_direto_no_engine(faq):
    m = faq.match("falar com atendente")
    assert m is not None
    assert m.intent_id == "falar_humano"
    assert m.follow_up_state == "encaminhar_humano"
```

### C19 — Rate limit não bloqueou

Verificar se `flag_modified` está realmente persistindo entre requests. O test `test_rate_limit_persists_across_calls` em `test_session_service.py` deve passar — se estiver passando mas o Telegram não bloqueia, o problema pode estar em o polling criar um novo `SessionLocal()` por mensagem que não vê as mudanças do commit anterior.

### C20 — "qual o preço do bitcoin?" sem resposta

O fallback deve sempre retornar uma mensagem. Verificar se `handle()` pode retornar um `HandleResult` com `response.body == ""`.

---

## S05-06 — Atualizar go_live_checklist.md

Substituir critérios manuais por referências aos testes automatizados:

```markdown
## Critérios de Produto (validados por pytest)
- [ ] `test_conversation_flows.py` — todos os testes passando
- [ ] `test_faq_stress.py` — 80+ variações cobertas
- [ ] `test_edge_cases.py` — edge cases passando
- [ ] `pytest tests/ -q` — 0 falhas, cobertura >= 80%
```

---

## Ordem de Execução

```
S05-05 → S05-01 → S05-02 → S05-03 → S05-04 → S05-06
```

S05-05 primeiro — corrigir bugs antes de escrever testes que dependem do comportamento correto.  
S05-01 é a fundação — `ConversationSimulator` antes dos testes de fluxo.  
S05-02, S05-03 e S05-04 são independentes entre si após S05-01.  
S05-06 fecha o sprint com checklist atualizado.

---

## Commits Atômicos Esperados

```
fix(faq,engine): bugs remanescentes C10 C17 C19 C20 [S05-05]
feat(tests): ConversationSimulator + fixture pipeline [S05-01]
test(flows): 20 cenários dogfooding automatizados [S05-02]
test(faq): stress tests 80+ variações linguísticas [S05-03]
test(edge): edge cases e inputs adversariais [S05-04]
docs(golive): critérios de produto substituídos por pytest [S05-06]
```

---

## Critérios de Aceite

- [ ] `ConversationSimulator.send()` simula conversa real via pipeline
- [ ] C01-C20 todos como testes pytest passando (exceto C03 que é manual por natureza — timeout real)
- [ ] 80+ variações de FAQ cobertas em `test_faq_stress.py`
- [ ] Edge cases: vazio, emoji, SQL injection, nome especial, sessões isoladas
- [ ] Fluxo de orçamento completo: lead gravado com todos os campos
- [ ] Rate limit testado via simulator sem Telegram
- [ ] 0 testes falhando
- [ ] Cobertura global >= 82%
- [ ] CI verde na branch `sprint/05-conversation-tests`
- [ ] `camisart-sprint-review` aprovado antes do merge
- [ ] Dogfooding manual vira validação de UX, não de funcionalidade
```
