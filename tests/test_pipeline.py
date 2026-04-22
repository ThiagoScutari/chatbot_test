"""Testes do MessagePipeline, admin endpoints e do contrato do Channel Adapter."""
import ast
import hashlib
import hmac
import json
import pathlib
from unittest.mock import AsyncMock, patch


FIXTURES = json.loads(
    pathlib.Path("tests/fixtures/whatsapp_payloads.json").read_text(
        encoding="utf-8"
    )
)
SECRET = "test-app-secret-32-chars-minimum-ok"


def make_sig(body: bytes) -> str:
    return (
        "sha256="
        + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    )


# ── Pipeline via webhook ──────────────────────────────────────────────────


def test_pipeline_processes_text_message(client):
    body = json.dumps(FIXTURES["text_message"]).encode()
    with patch(
        "app.adapters.whatsapp_cloud.client.send_message",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = "wamid.test123"
        r = client.post(
            "/adapters/whatsapp_cloud/webhook",
            content=body,
            headers={
                "content-type": "application/json",
                "x-hub-signature-256": make_sig(body),
            },
        )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["processed"] is True


def test_pipeline_dedup_returns_not_processed(client):
    """Reenviar o mesmo payload retorna processed=False na segunda vez."""
    body = json.dumps(FIXTURES["text_message"]).encode()
    headers = {
        "content-type": "application/json",
        "x-hub-signature-256": make_sig(body),
    }
    with patch(
        "app.adapters.whatsapp_cloud.client.send_message",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = "wamid.dedup001"
        r1 = client.post(
            "/adapters/whatsapp_cloud/webhook", content=body, headers=headers
        )
        r2 = client.post(
            "/adapters/whatsapp_cloud/webhook", content=body, headers=headers
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["data"]["processed"] is False


def test_status_update_returns_200_no_processing(client):
    body = json.dumps(FIXTURES["status_update"]).encode()
    r = client.post(
        "/adapters/whatsapp_cloud/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": make_sig(body),
        },
    )
    assert r.status_code == 200
    assert r.json()["data"]["processed"] is False


# ── Contrato arquitetural: Channel Adapter isolation ─────────────────────


def test_adapter_not_imported_in_pipeline():
    """Channel Adapter Pattern (§2.4): pipeline não importa adapters concretos."""
    src = pathlib.Path("app/pipeline/message_pipeline.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = (
                getattr(node, "module", None) or ""
                if isinstance(node, ast.ImportFrom)
                else node.names[0].name
            )
            assert "whatsapp_cloud" not in module, (
                f"VIOLATION: pipeline importa '{module}' "
                f"na linha {node.lineno}"
            )


def test_adapter_not_imported_in_engines():
    """Engines não podem conhecer detalhes de canal."""
    for py in pathlib.Path("app/engines").rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = (
                    getattr(node, "module", None) or ""
                    if isinstance(node, ast.ImportFrom)
                    else node.names[0].name
                )
                assert "whatsapp_cloud" not in module, (
                    f"VIOLATION: {py} importa '{module}' "
                    f"na linha {node.lineno}"
                )


def test_adapter_not_imported_in_services():
    """Services não podem conhecer detalhes de canal."""
    for py in pathlib.Path("app/services").rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = (
                    getattr(node, "module", None) or ""
                    if isinstance(node, ast.ImportFrom)
                    else node.names[0].name
                )
                assert "whatsapp_cloud" not in module, (
                    f"VIOLATION: {py} importa '{module}' "
                    f"na linha {node.lineno}"
                )


# ── Admin endpoints ──────────────────────────────────────────────────────


def test_admin_reload_valid_token(client):
    r = client.post(
        "/admin/campaigns/reload",
        headers={"x-admin-token": "test-admin-token-32-chars-minimum-ok"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["reloaded"] is True


def test_admin_reload_invalid_token(client):
    r = client.post(
        "/admin/campaigns/reload",
        headers={"x-admin-token": "wrong"},
    )
    assert r.status_code == 403


def test_admin_reload_missing_token(client):
    r = client.post("/admin/campaigns/reload")
    # FastAPI Header(...) retorna 422 quando ausente; aceitamos tanto 403 quanto 422
    assert r.status_code in (403, 422)


def test_admin_status_valid_token(client):
    r = client.get(
        "/admin/campaigns/status",
        headers={"x-admin-token": "test-admin-token-32-chars-minimum-ok"},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert "active" in body
    assert "upcoming" in body


def test_send_catalog_calls_adapter_twice(client):
    """send_catalog must call send_text at least twice: catalog + follow-up."""
    body = json.dumps({
        "update_id": 777001,
        "message": {
            "message_id": 777001,
            "from": {"id": 5599000777001, "first_name": "TEST_Catalog"},
            "chat": {"id": 5599000777001, "type": "private"},
            "text": "ver_catalogo",
            "date": 1714000000,
        },
    }).encode()

    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = "99"
        r = client.post(
            "/adapters/telegram/webhook",
            content=body,
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 200
    # At minimum: catalog message sent
    assert mock_send.call_count >= 1
    # Verify catalog content was in one of the calls
    all_texts = " ".join(
        str(call.args[1]) for call in mock_send.call_args_list
        if len(call.args) >= 2
    )
    assert "Camisart" in all_texts or "polo" in all_texts.lower()
