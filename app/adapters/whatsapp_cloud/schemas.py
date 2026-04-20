"""Pydantic models para o formato de webhook da Meta Cloud API.

Baseado em https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
"""
from typing import Any

from pydantic import BaseModel, Field


class WhatsAppTextPayload(BaseModel):
    body: str


class WhatsAppButtonReply(BaseModel):
    id: str
    title: str


class WhatsAppListReply(BaseModel):
    id: str
    title: str
    description: str | None = None


class WhatsAppInteractive(BaseModel):
    type: str  # "button_reply" | "list_reply"
    button_reply: WhatsAppButtonReply | None = None
    list_reply: WhatsAppListReply | None = None


class WhatsAppContactProfile(BaseModel):
    name: str | None = None


class WhatsAppContact(BaseModel):
    wa_id: str
    profile: WhatsAppContactProfile | None = None


class WhatsAppMessage(BaseModel):
    id: str
    from_: str = Field(alias="from")
    timestamp: str
    type: str  # "text" | "interactive" | "image" | ...
    text: WhatsAppTextPayload | None = None
    interactive: WhatsAppInteractive | None = None

    model_config = {"populate_by_name": True}


class WhatsAppStatus(BaseModel):
    id: str
    status: str  # "sent" | "delivered" | "read" | "failed"


class WhatsAppValue(BaseModel):
    messaging_product: str | None = None
    messages: list[WhatsAppMessage] | None = None
    contacts: list[WhatsAppContact] | None = None
    statuses: list[WhatsAppStatus] | None = None
    metadata: dict[str, Any] | None = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    id: str
    changes: list[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: list[WhatsAppEntry]
