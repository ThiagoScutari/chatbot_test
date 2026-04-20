from app.adapters.whatsapp_cloud.adapter import WhatsAppCloudAdapter
from app.schemas.messaging import OutboundMessage


adapter = WhatsAppCloudAdapter()


def make_outbound(response: dict) -> OutboundMessage:
    return OutboundMessage(
        channel_id="whatsapp_cloud",
        channel_user_id="5591999990001",
        response=response,
    )


def test_buttons_payload():
    out = make_outbound(
        {
            "type": "buttons",
            "body": "Como posso ajudar?",
            "buttons": [
                {"id": "a", "title": "Opção A"},
                {"id": "b", "title": "Opção B"},
                {"id": "c", "title": "Opção C"},
            ],
        }
    )
    payload = adapter._build_meta_payload(out)
    assert payload["type"] == "interactive"
    assert payload["interactive"]["type"] == "button"
    assert len(payload["interactive"]["action"]["buttons"]) == 3


def test_buttons_truncated_to_3():
    out = make_outbound(
        {
            "type": "buttons",
            "body": "Opções",
            "buttons": [{"id": str(i), "title": f"Op {i}"} for i in range(5)],
        }
    )
    payload = adapter._build_meta_payload(out)
    assert len(payload["interactive"]["action"]["buttons"]) == 3


def test_list_payload():
    out = make_outbound(
        {
            "type": "list",
            "body": "Selecione o segmento:",
            "list_button_label": "Ver segmentos",
            "list_items": [
                {"id": "corp", "title": "Corporativo"},
                {"id": "saude", "title": "Saúde"},
            ],
        }
    )
    payload = adapter._build_meta_payload(out)
    assert payload["interactive"]["type"] == "list"
    rows = payload["interactive"]["action"]["sections"][0]["rows"]
    assert len(rows) == 2


def test_text_payload_fallback():
    out = make_outbound({"type": "text", "body": "Olá!"})
    payload = adapter._build_meta_payload(out)
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "Olá!"


def test_button_title_truncated_to_20_chars():
    out = make_outbound(
        {
            "type": "buttons",
            "body": "Teste",
            "buttons": [{"id": "x", "title": "Este título é muito longo demais"}],
        }
    )
    payload = adapter._build_meta_payload(out)
    title = payload["interactive"]["action"]["buttons"][0]["reply"]["title"]
    assert len(title) <= 20
