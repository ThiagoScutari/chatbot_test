from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.telegram.adapter import TelegramAdapter
from app.schemas.messaging import OutboundMessage


adapter = TelegramAdapter()


VALID_TEXT_UPDATE = {
    "update_id": 123456,
    "message": {
        "message_id": 1,
        "from": {"id": 5591999990001, "first_name": "TEST_Maria"},
        "chat": {"id": 5591999990001, "type": "private"},
        "text": "qual o preço da polo?",
        "date": 1714000000,
    },
}

NON_TEXT_UPDATE = {
    "update_id": 123457,
    "message": {
        "message_id": 2,
        "from": {"id": 5591999990001, "first_name": "TEST_Maria"},
        "chat": {"id": 5591999990001, "type": "private"},
        "date": 1714000000,
        # sem campo "text" — foto, sticker, etc.
    },
}

UPDATE_NO_MESSAGE = {
    "update_id": 123458,
    # sem chave "message" — channel_post, edited_message, etc.
}


@pytest.mark.asyncio
async def test_parse_text_message():
    inbound = await adapter.parse_inbound(VALID_TEXT_UPDATE, {})
    assert inbound is not None
    assert inbound.channel_id == "telegram"
    assert inbound.content == "qual o preço da polo?"
    assert inbound.channel_user_id == "5591999990001"
    assert inbound.display_name == "TEST_Maria"
    assert inbound.channel_message_id == "1"


@pytest.mark.asyncio
async def test_parse_non_text_returns_none():
    result = await adapter.parse_inbound(NON_TEXT_UPDATE, {})
    assert result is None


@pytest.mark.asyncio
async def test_parse_no_message_returns_none():
    result = await adapter.parse_inbound(UPDATE_NO_MESSAGE, {})
    assert result is None


def test_verify_auth_no_secret_passes():
    # TELEGRAM_WEBHOOK_SECRET vazio em .env de teste — não deve levantar
    adapter.verify_auth(b"payload", {})


def test_verify_auth_valid_secret(monkeypatch):
    monkeypatch.setattr(
        "app.adapters.telegram.adapter.settings.TELEGRAM_WEBHOOK_SECRET",
        "mysecret",
    )
    adapter.verify_auth(
        b"p", {"x-telegram-bot-api-secret-token": "mysecret"}
    )  # sem exceção


def test_verify_auth_invalid_secret(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        "app.adapters.telegram.adapter.settings.TELEGRAM_WEBHOOK_SECRET",
        "mysecret",
    )
    with pytest.raises(HTTPException) as exc:
        adapter.verify_auth(
            b"p", {"x-telegram-bot-api-secret-token": "wrong"}
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_send_converts_buttons_to_text():
    outbound = OutboundMessage(
        channel_id="telegram",
        channel_user_id="5591999990001",
        response={
            "type": "buttons",
            "body": "Como posso ajudar?",
            "buttons": [
                {"id": "consultar_pedido", "title": "Meu pedido"},
                {"id": "ver_catalogo", "title": "Ver catálogo"},
                {"id": "falar_humano", "title": "Falar com atendente"},
            ],
        },
    )
    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "42"
        await adapter.send(outbound)
        call_args = mock.call_args
        sent_text = call_args[0][1]  # segundo arg posicional = text
        assert "1." in sent_text
        assert "Meu pedido" in sent_text


@pytest.mark.asyncio
async def test_send_text_only():
    outbound = OutboundMessage(
        channel_id="telegram",
        channel_user_id="5591999990002",
        response={"type": "text", "body": "Olá!"},
    )
    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "11"
        result = await adapter.send(outbound)
        assert result == "11"
        assert mock.call_args[0][1] == "Olá!"


def test_adapter_not_imported_in_pipeline_or_engines():
    """Channel Adapter Pattern: isolamento também vale para telegram."""
    import ast
    import pathlib

    for src_file in [
        "app/pipeline/message_pipeline.py",
        "app/engines/regex_engine.py",
        "app/engines/state_machine.py",
        "app/engines/campaign_engine.py",
    ]:
        src = pathlib.Path(src_file).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = (
                    getattr(node, "module", None) or ""
                    if isinstance(node, ast.ImportFrom)
                    else node.names[0].name
                )
                assert "telegram" not in module, (
                    f"VIOLATION: {src_file} importa telegram adapter "
                    f"na linha {node.lineno}"
                )
