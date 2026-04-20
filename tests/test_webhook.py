import hashlib
import hmac
import json
from pathlib import Path


FIXTURES = json.loads(
    Path("tests/fixtures/whatsapp_payloads.json").read_text(encoding="utf-8")
)
SECRET = "test-app-secret-32-chars-minimum-ok"


def make_sig(body: bytes) -> str:
    return (
        "sha256="
        + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    )


def test_verify_webhook_valid_token(client):
    r = client.get(
        "/adapters/whatsapp_cloud/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "challenge_abc",
        },
    )
    assert r.status_code == 200
    assert r.text == "challenge_abc"


def test_verify_webhook_invalid_token(client):
    r = client.get(
        "/adapters/whatsapp_cloud/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "challenge_abc",
        },
    )
    assert r.status_code == 403


def test_receive_message_valid_hmac(client):
    body = json.dumps(FIXTURES["text_message"]).encode()
    r = client.post(
        "/adapters/whatsapp_cloud/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": make_sig(body),
        },
    )
    assert r.status_code == 200


def test_receive_message_invalid_hmac(client):
    body = json.dumps(FIXTURES["text_message"]).encode()
    r = client.post(
        "/adapters/whatsapp_cloud/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": "sha256=invalido",
        },
    )
    assert r.status_code == 403


def test_receive_message_no_hmac(client):
    body = json.dumps(FIXTURES["text_message"]).encode()
    r = client.post(
        "/adapters/whatsapp_cloud/webhook",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 403


def test_receive_status_update_no_processing(client):
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


def test_receive_button_reply(client):
    body = json.dumps(FIXTURES["button_reply"]).encode()
    r = client.post(
        "/adapters/whatsapp_cloud/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": make_sig(body),
        },
    )
    assert r.status_code == 200
