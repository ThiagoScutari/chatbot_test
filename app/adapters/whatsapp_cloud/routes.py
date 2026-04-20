"""Endpoints FastAPI do adapter WhatsApp Cloud.

Paths canônicos conforme §4.6 do spec:
  GET  /adapters/whatsapp_cloud/webhook  → handshake Meta
  POST /adapters/whatsapp_cloud/webhook  → recebimento de mensagens
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.adapters.whatsapp_cloud.adapter import WhatsAppCloudAdapter
from app.config import settings
from app.schemas.response import StandardResponse


router = APIRouter(prefix="/adapters/whatsapp_cloud", tags=["whatsapp"])
adapter = WhatsAppCloudAdapter()


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
) -> PlainTextResponse:
    """Handshake inicial da Meta — responde o challenge quando o token bate."""
    if (
        hub_mode == "subscribe"
        and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN
    ):
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verify token inválido.")


@router.post("/webhook", status_code=200)
async def receive_message(request: Request) -> StandardResponse:
    """Recebe mensagens do WhatsApp Cloud API.

    1. Valida HMAC-SHA256 via adapter.verify_auth
    2. Parse em InboundMessage canônica
    3. (S01-05) despachar para MessagePipeline
    """
    raw = await request.body()
    adapter.verify_auth(raw, dict(request.headers))
    payload = json.loads(raw) if raw else {}
    inbound = await adapter.parse_inbound(payload, dict(request.headers))

    if inbound is None:
        return StandardResponse(
            data={"received": True, "processed": False}
        )

    # Pipeline wiring é feito no S01-05 — por ora, apenas confirmamos recebimento.
    return StandardResponse(
        data={
            "received": True,
            "processed": False,
            "inbound_id": inbound.channel_message_id,
        }
    )
