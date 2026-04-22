"""LLMRouter — testes com mocks obrigatórios.

REGRA ABSOLUTA: nenhum teste chama a API Anthropic real.
Todo teste que envolve LLMRouter usa mock.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engines.llm_router import LLMClassification, LLMRouter


CONFIG_PATH = Path("app/knowledge/llm_config.json")


def make_mock_response(intent_id: str | None, confidence: float) -> MagicMock:
    """Cria mock da resposta da API Anthropic."""
    content = json.dumps(
        {
            "intent_id": intent_id,
            "confidence": confidence,
            "reasoning": f"test mock for {intent_id}",
        }
    )
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=content)]
    return mock_msg


@pytest.fixture
def router():
    # Client mockado — nunca instancia cliente real com API key
    fake_client = MagicMock()
    fake_client.messages = MagicMock()
    fake_client.messages.create = AsyncMock()
    return LLMRouter(CONFIG_PATH, client=fake_client)


@pytest.mark.asyncio
async def test_classifica_intent_com_alta_confianca(router):
    with patch.object(
        router._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = make_mock_response("preco_polo", 0.95)
        result = await router.classify_intent(
            message="quanto custa aquela camisa branca?",
            session_context={},
            known_intents=["preco_polo", "endereco", "bordado_prazo"],
        )
    assert result.intent_id == "preco_polo"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_retorna_none_para_fora_do_escopo(router):
    with patch.object(
        router._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = make_mock_response(None, 0.95)
        result = await router.classify_intent(
            message="qual o preço do bitcoin?",
            session_context={},
            known_intents=["preco_polo", "endereco"],
        )
    assert result.intent_id is None


@pytest.mark.asyncio
async def test_fallback_em_erro_de_api(router):
    """Se API falhar, retorna classificação vazia sem levantar exceção."""
    with patch.object(
        router._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.side_effect = Exception("Connection timeout")
        result = await router.classify_intent(
            message="qualquer coisa",
            session_context={},
            known_intents=["preco_polo"],
        )
    assert result.intent_id is None
    assert result.confidence == 0.0
    assert router.stats["errors"] == 1


@pytest.mark.asyncio
async def test_fallback_em_json_invalido(router):
    """Se API retornar JSON inválido, retorna classificação vazia."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="isso não é json")]
    with patch.object(
        router._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_msg
        result = await router.classify_intent(
            message="qualquer coisa",
            session_context={},
            known_intents=["preco_polo"],
        )
    assert result.intent_id is None
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_intent_id_invalido_descartado(router):
    """Se LLM retornar intent_id que não existe na lista, descartar."""
    with patch.object(
        router._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = make_mock_response("intent_inventado", 0.99)
        result = await router.classify_intent(
            message="mensagem qualquer",
            session_context={},
            known_intents=["preco_polo", "endereco"],
        )
    assert result.intent_id is None
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_contexto_incluido_no_prompt(router):
    """Verifica que o contexto da sessão é incluído no prompt enviado."""
    with patch.object(
        router._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = make_mock_response("preco_polo", 0.9)
        await router.classify_intent(
            message="e quanto fica com bordado?",
            session_context={"last_messages": ["quero comprar polo"]},
            known_intents=["preco_polo", "bordado_prazo"],
        )
    call_kwargs = mock_create.call_args
    messages_arg = call_kwargs.kwargs.get("messages")
    prompt_text = str(messages_arg)
    assert "polo" in prompt_text.lower()


@pytest.mark.asyncio
async def test_stats_contabilizados_por_threshold(router):
    """Classificações atualizam stats de high/medium/low corretamente."""
    with patch.object(
        router._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = make_mock_response("preco_polo", 0.95)
        await router.classify_intent("x", {}, ["preco_polo"])
        mock_create.return_value = make_mock_response("preco_polo", 0.70)
        await router.classify_intent("y", {}, ["preco_polo"])
        mock_create.return_value = make_mock_response("preco_polo", 0.45)
        await router.classify_intent("z", {}, ["preco_polo"])
    assert router.stats["total"] == 3
    assert router.stats["high"] == 1
    assert router.stats["medium"] == 1
    assert router.stats["low"] == 1


@pytest.mark.asyncio
async def test_strip_markdown_fences_json(router):
    """Respostas com code fences ```json são parseadas corretamente."""
    mock_msg = MagicMock()
    mock_msg.content = [
        MagicMock(
            text='```json\n{"intent_id": "preco_polo", "confidence": 0.9, "reasoning": "x"}\n```'
        )
    ]
    with patch.object(
        router._client.messages, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_msg
        result = await router.classify_intent(
            "qualquer", {}, ["preco_polo"]
        )
    assert result.intent_id == "preco_polo"
    assert result.confidence == 0.9


# ── Testes de integração: pipeline com LLMRouter mockado ──────────────────

@pytest.mark.asyncio
async def test_pipeline_usa_llm_quando_faq_retorna_none(sim, pipeline):
    """Mensagem sem match no FAQ → LLMRouter é chamado."""
    fake_client = MagicMock()
    fake_client.messages = MagicMock()
    fake_client.messages.create = AsyncMock()
    pipeline._llm_router = LLMRouter(CONFIG_PATH, client=fake_client)

    mock_classification = LLMClassification(
        intent_id="preco_polo",
        confidence=0.90,
        reasoning="test",
    )
    with patch.object(
        pipeline._llm_router,
        "classify_intent",
        new_callable=AsyncMock,
        return_value=mock_classification,
    ) as mock_classify:
        await sim.send("/start")
        await sim.send("Thiago")
        # Mensagem que não casa com regex mas LLM classifica como preco_polo
        await sim.send("poderia me ajudar com valores de uma camisa xyz?")

    assert mock_classify.called
    # A resposta deve vir do template preco_polo (R$ 45, etc)
    assert sim.last_response


@pytest.mark.asyncio
async def test_pipeline_sem_llm_funciona_normalmente(sim):
    """Pipeline sem LLMRouter configurado funciona igual ao Sprint 05."""
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço da polo?")
    assert any(w in sim.last_response for w in ["45", "42", "polo", "Polo"])


@pytest.mark.asyncio
async def test_pipeline_llm_com_baixa_confianca_pede_confirmacao(sim, pipeline):
    """Confiança entre low e medium → pergunta 'Você quis dizer X?'."""
    fake_client = MagicMock()
    fake_client.messages = MagicMock()
    fake_client.messages.create = AsyncMock()
    pipeline._llm_router = LLMRouter(CONFIG_PATH, client=fake_client)

    mock_classification = LLMClassification(
        intent_id="preco_polo",
        confidence=0.45,  # entre low (0.40) e medium (0.60)
        reasoning="test",
    )
    with patch.object(
        pipeline._llm_router,
        "classify_intent",
        new_callable=AsyncMock,
        return_value=mock_classification,
    ):
        await sim.send("/start")
        await sim.send("Thiago")
        await sim.send("mensagem ambígua xyz")

    # Deve pedir confirmação
    assert "quer saber sobre" in sim.last_response.lower() or sim.last_buttons


@pytest.mark.asyncio
async def test_pipeline_llm_confianca_muito_baixa_fallback(sim, pipeline):
    """Confiança < 0.40 → fallback para state_machine (menu/fallback)."""
    fake_client = MagicMock()
    fake_client.messages = MagicMock()
    fake_client.messages.create = AsyncMock()
    pipeline._llm_router = LLMRouter(CONFIG_PATH, client=fake_client)

    mock_classification = LLMClassification(
        intent_id=None,
        confidence=0.0,
        reasoning="test",
    )
    with patch.object(
        pipeline._llm_router,
        "classify_intent",
        new_callable=AsyncMock,
        return_value=mock_classification,
    ):
        await sim.send("/start")
        await sim.send("Thiago")
        await sim.send("asdkjhaskdjh")

    # Estado permanece MENU, resposta vem do fallback
    assert sim.state == "menu"
    assert sim.last_response


@pytest.mark.asyncio
async def test_llm_never_called_when_faq_matches(sim, pipeline):
    """FAQ com match não chama LLMRouter — verificado por mock."""
    fake_client = MagicMock()
    fake_client.messages = MagicMock()
    fake_client.messages.create = AsyncMock()
    pipeline._llm_router = LLMRouter(CONFIG_PATH, client=fake_client)

    with patch.object(
        pipeline._llm_router,
        "classify_intent",
        new_callable=AsyncMock,
    ) as mock_classify:
        await sim.send("/start")
        await sim.send("Thiago")
        await sim.send("qual o preço da polo?")  # FAQ match

    mock_classify.assert_not_called()


def test_intent_ids_do_faq_inclui_todos():
    """FAQEngine.intent_ids() retorna todos os intents carregados."""
    from app.engines.regex_engine import FAQEngine

    faq = FAQEngine(Path("app/knowledge/faq.json"))
    ids = faq.intent_ids()
    assert "preco_polo" in ids
    assert "endereco" in ids
    assert "falar_humano" in ids
    assert len(ids) >= 10


def test_match_by_id_retorna_faq_match():
    """FAQEngine.match_by_id retorna FAQMatch com intent_id correto."""
    from app.engines.regex_engine import FAQEngine

    faq = FAQEngine(Path("app/knowledge/faq.json"))
    m = faq.match_by_id("preco_polo")
    assert m is not None
    assert m.intent_id == "preco_polo"
    assert m.response.body


def test_match_by_id_retorna_none_para_id_invalido():
    from app.engines.regex_engine import FAQEngine

    faq = FAQEngine(Path("app/knowledge/faq.json"))
    assert faq.match_by_id("inexistente") is None
