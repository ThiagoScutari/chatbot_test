from unittest.mock import AsyncMock, patch


VALID_TEXT_UPDATE = {
    "update_id": 999001,
    "message": {
        "message_id": 1,
        "from": {"id": 5591999990099, "first_name": "TEST_Integration"},
        "chat": {"id": 5591999990099, "type": "private"},
        "text": "qual o preço da polo?",
        "date": 1714000000,
    },
}

NON_TEXT_UPDATE = {
    "update_id": 999002,
    "message": {
        "message_id": 2,
        "from": {"id": 5591999990099, "first_name": "TEST_Integration"},
        "chat": {"id": 5591999990099, "type": "private"},
        "date": 1714000000,
    },
}


def test_telegram_webhook_text_returns_200(client):
    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = "42"
        r = client.post("/adapters/telegram/webhook", json=VALID_TEXT_UPDATE)
    assert r.status_code == 200
    assert r.json()["data"]["received"] is True


def test_telegram_webhook_non_text_returns_200_no_send(client):
    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock,
    ) as mock_send:
        r = client.post("/adapters/telegram/webhook", json=NON_TEXT_UPDATE)
    assert r.status_code == 200
    mock_send.assert_not_called()


def test_telegram_webhook_triggers_send(client):
    """FAQ match deve disparar send_text pelo menos uma vez."""
    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = "43"
        r = client.post("/adapters/telegram/webhook", json=VALID_TEXT_UPDATE)
    assert r.status_code == 200
    assert mock_send.call_count >= 1


def test_telegram_webhook_invalid_secret_returns_403(client, monkeypatch):
    monkeypatch.setattr(
        "app.adapters.telegram.adapter.settings.TELEGRAM_WEBHOOK_SECRET",
        "mysecret",
    )
    r = client.post(
        "/adapters/telegram/webhook",
        json=VALID_TEXT_UPDATE,
        headers={"x-telegram-bot-api-secret-token": "wrong"},
    )
    assert r.status_code == 403


def test_telegram_routes_no_whatsapp_import():
    """Channel Adapter Pattern: telegram/routes não importa whatsapp_cloud."""
    import ast
    import pathlib

    src = pathlib.Path("app/adapters/telegram/routes.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            assert "whatsapp_cloud" not in module, (
                f"VIOLATION: telegram/routes importa whatsapp_cloud "
                f"linha {node.lineno}"
            )
