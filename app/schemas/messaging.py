from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """Mensagem canônica canal-agnóstica — entrada no MessagePipeline."""

    channel_id: Literal["whatsapp_cloud", "kommo", "instagram_dm"]
    channel_message_id: str
    channel_user_id: str
    display_name: str | None = None
    content: str
    timestamp: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OutboundMessage(BaseModel):
    """Mensagem canônica canal-agnóstica — saída do MessagePipeline."""

    channel_id: str
    channel_user_id: str
    channel_message_id: str | None = None  # preenchido após adapter.send()
    response: dict[str, Any]  # FAQResponse serializado (type, body, buttons, ...)
