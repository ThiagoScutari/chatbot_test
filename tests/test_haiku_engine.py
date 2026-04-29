"""Tests for HaikuEngine — all mocked, zero API calls."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engines.haiku_engine import HaikuEngine


def make_mock_response(json_content: dict) -> MagicMock:
    """Create a mock Anthropic API response."""
    mock = MagicMock()
    mock.content = [MagicMock(text=json.dumps(json_content, ensure_ascii=False))]
    mock.usage = MagicMock(input_tokens=100, output_tokens=50)
    return mock


@pytest.fixture
def engine(tmp_path):
    """HaikuEngine with mock client and temp prompt."""
    prompt_file = tmp_path / "test_prompt.md"
    prompt_file.write_text("You are a test assistant.", encoding="utf-8")
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock()
    return HaikuEngine(prompt_path=prompt_file, client=mock_client)


@pytest.mark.asyncio
async def test_valid_json_response(engine) -> None:
    """Valid JSON from Haiku is parsed correctly."""
    response_json = {
        "resposta": "Olá! Como posso ajudar?",
        "dados_extraidos": {"nome": "Carlos"},
        "acao": "continuar",
        "intent": "saudacao",
    }
    engine._client.messages.create.return_value = make_mock_response(response_json)

    result = await engine.process("oi", [], {})

    assert result.resposta == "Olá! Como posso ajudar?"
    assert result.dados_extraidos == {"nome": "Carlos"}
    assert result.acao == "continuar"
    assert result.intent == "saudacao"
    assert result.tokens_input == 100
    assert result.tokens_output == 50


@pytest.mark.asyncio
async def test_json_with_backticks(engine) -> None:
    """JSON wrapped in ```json...``` is cleaned and parsed."""
    raw = (
        '```json\n'
        '{"resposta": "Oi!", "dados_extraidos": {}, '
        '"acao": "continuar", "intent": "saudacao"}\n'
        '```'
    )
    mock = MagicMock()
    mock.content = [MagicMock(text=raw)]
    mock.usage = MagicMock(input_tokens=50, output_tokens=30)
    engine._client.messages.create.return_value = mock

    result = await engine.process("oi", [], {})
    assert result.resposta == "Oi!"


@pytest.mark.asyncio
async def test_malformed_json_fallback(engine) -> None:
    """Malformed JSON falls back to raw text as response."""
    mock = MagicMock()
    mock.content = [MagicMock(text="Isso não é JSON nenhum")]
    mock.usage = MagicMock(input_tokens=50, output_tokens=30)
    engine._client.messages.create.return_value = mock

    result = await engine.process("oi", [], {})
    assert result.resposta == "Isso não é JSON nenhum"
    assert result.intent == "parse_error"


@pytest.mark.asyncio
async def test_api_error_raises(engine) -> None:
    """API error propagates (pipeline handles fallback)."""
    engine._client.messages.create.side_effect = Exception("Connection timeout")

    with pytest.raises(Exception, match="Connection timeout"):
        await engine.process("oi", [], {})


@pytest.mark.asyncio
async def test_funil_status_included(engine) -> None:
    """Session data is formatted and included in system prompt."""
    response_json = {
        "resposta": "Oi Carlos!",
        "dados_extraidos": {},
        "acao": "continuar",
        "intent": "saudacao",
    }
    engine._client.messages.create.return_value = make_mock_response(response_json)

    await engine.process("oi", [], {"nome": "Carlos", "segmento": "saude"})

    call_kwargs = engine._client.messages.create.call_args
    system_arg = call_kwargs.kwargs.get("system", "")
    assert "Carlos" in system_arg
    assert "saude" in system_arg


@pytest.mark.asyncio
async def test_conversation_history_forwarded(engine) -> None:
    """Conversation history is sent as messages to Haiku."""
    response_json = {
        "resposta": "Tudo bem!",
        "dados_extraidos": {},
        "acao": "continuar",
        "intent": "saudacao",
    }
    engine._client.messages.create.return_value = make_mock_response(response_json)

    history = [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "Olá!"},
    ]
    await engine.process("tudo bem?", history, {})

    call_kwargs = engine._client.messages.create.call_args
    messages = call_kwargs.kwargs.get("messages", [])
    assert len(messages) == 3
    assert messages[-1]["content"] == "tudo bem?"


@pytest.mark.asyncio
async def test_lead_completo_action(engine) -> None:
    """lead_completo action is returned when Haiku indicates."""
    response_json = {
        "resposta": "Orçamento confirmado! Um consultor entrará em contato.",
        "dados_extraidos": {},
        "acao": "lead_completo",
        "intent": "confirmou_orcamento",
    }
    engine._client.messages.create.return_value = make_mock_response(response_json)

    result = await engine.process("sim, tá certo", [], {})
    assert result.acao == "lead_completo"


@pytest.mark.asyncio
async def test_transferir_humano_action(engine) -> None:
    """transferir_humano action is returned for complaints."""
    response_json = {
        "resposta": "Sinto muito! Vou te encaminhar para nosso atendente.",
        "dados_extraidos": {},
        "acao": "transferir_humano",
        "intent": "reclamacao",
    }
    engine._client.messages.create.return_value = make_mock_response(response_json)

    result = await engine.process("o bordado veio errado!", [], {})
    assert result.acao == "transferir_humano"


@pytest.mark.asyncio
async def test_json_with_text_before(engine) -> None:
    """JSON with text before it is extracted correctly."""
    raw = (
        'Aqui está minha resposta:\n'
        '{"resposta": "Oi!", "dados_extraidos": {}, '
        '"acao": "continuar", "intent": "saudacao"}'
    )
    mock = MagicMock()
    mock.content = [MagicMock(text=raw)]
    mock.usage = MagicMock(input_tokens=50, output_tokens=30)
    engine._client.messages.create.return_value = mock

    result = await engine.process("oi", [], {})
    assert result.resposta == "Oi!"
    assert result.intent == "saudacao"


@pytest.mark.asyncio
async def test_json_nested_braces(engine) -> None:
    """Nested JSON objects are parsed correctly."""
    raw = (
        '{"resposta": "Polo R$42,00", '
        '"dados_extraidos": {"nome": "Carlos", "produto": "polo"}, '
        '"acao": "continuar", "intent": "preco"}'
    )
    mock = MagicMock()
    mock.content = [MagicMock(text=raw)]
    mock.usage = MagicMock(input_tokens=50, output_tokens=30)
    engine._client.messages.create.return_value = mock

    result = await engine.process("quanto custa polo", [], {})
    assert result.dados_extraidos["nome"] == "Carlos"
    assert result.dados_extraidos["produto"] == "polo"
