"""MessageService — persistência de mensagens in/out."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.session import Session as SessionModel
from app.schemas.messaging import InboundMessage


def record_inbound(
    db: Session,
    session: SessionModel,
    inbound: InboundMessage,
    matched_intent_id: str | None = None,
    state_before: str | None = None,
    state_after: str | None = None,
) -> Message:
    """Persiste a mensagem de entrada com intent casado e estados pré/pós."""
    message = Message(
        session_id=session.id,
        direction="in",
        channel_id=inbound.channel_id,
        channel_message_id=inbound.channel_message_id,
        content=inbound.content,
        matched_intent_id=matched_intent_id,
        state_before=state_before,
        state_after=state_after,
        raw_payload=inbound.raw_payload,
    )
    db.add(message)
    db.flush()
    return message


def record_outbound(
    db: Session,
    session: SessionModel,
    content: str,
    state_before: str | None = None,
    state_after: str | None = None,
    channel_message_id: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> Message:
    """Persiste a resposta enviada ao cliente."""
    message = Message(
        session_id=session.id,
        direction="out",
        channel_id=session.channel_id,
        channel_message_id=channel_message_id,
        content=content,
        state_before=state_before,
        state_after=state_after,
        raw_payload=raw_payload,
    )
    db.add(message)
    db.flush()
    return message


def already_processed(
    db: Session, channel_id: str, channel_message_id: str
) -> bool:
    """True se a mensagem (channel_id, channel_message_id) já foi registrada."""
    existing = (
        db.query(Message)
        .filter(
            Message.channel_id == channel_id,
            Message.channel_message_id == channel_message_id,
        )
        .first()
    )
    return existing is not None
