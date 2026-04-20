from datetime import datetime, timezone

from app.models.session import Session as SessionModel
from app.schemas.messaging import InboundMessage
from app.services.message_service import (
    already_processed,
    record_inbound,
    record_outbound,
)


def _inbound() -> InboundMessage:
    return InboundMessage(
        channel_id="whatsapp_cloud",
        channel_message_id="wamid.msg001",
        channel_user_id="5591222221001",
        display_name="TEST_Cliente",
        content="qual o preço da polo?",
        timestamp=datetime.now(timezone.utc),
        raw_payload={"fixture": True},
    )


def test_record_inbound_persists_intent_and_states(db):
    s = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591222221001"
    )
    db.add(s)
    db.flush()

    msg = record_inbound(
        db, s, _inbound(),
        matched_intent_id="preco_polo",
        state_before="inicio",
        state_after="menu",
    )
    assert msg.direction == "in"
    assert msg.matched_intent_id == "preco_polo"
    assert msg.state_before == "inicio"
    assert msg.state_after == "menu"
    assert msg.raw_payload == {"fixture": True}


def test_record_outbound(db):
    s = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591222221002"
    )
    db.add(s)
    db.flush()

    out = record_outbound(
        db, s, content="Olá!", state_before="inicio", state_after="aguarda_nome"
    )
    assert out.direction == "out"
    assert out.content == "Olá!"


def test_already_processed_true_after_insert(db):
    s = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591222221003"
    )
    db.add(s)
    db.flush()

    record_inbound(db, s, _inbound(), matched_intent_id="preco_polo")
    assert already_processed(db, "whatsapp_cloud", "wamid.msg001") is True


def test_already_processed_false_when_missing(db):
    assert already_processed(db, "whatsapp_cloud", "wamid.does_not_exist") is False
