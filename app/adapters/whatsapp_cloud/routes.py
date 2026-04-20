"""Endpoints FastAPI do adapter WhatsApp Cloud.

Paths canônicos conforme §4.6 do spec:
  GET  /adapters/whatsapp_cloud/webhook  → handshake Meta
  POST /adapters/whatsapp_cloud/webhook  → recebimento de mensagens
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session as DbSession

from app.adapters.whatsapp_cloud.adapter import WhatsAppCloudAdapter
from app.config import settings
from app.database import get_db
from app.schemas.response import StandardResponse


logger = logging.getLogger(__name__)

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
async def receive_message(
    request: Request,
    db: DbSession = Depends(get_db),
) -> StandardResponse:
    """Recebe mensagens do WhatsApp Cloud API.

    1. Valida HMAC-SHA256 via adapter.verify_auth
    2. Parse em InboundMessage canônica (status updates → None)
    3. Despacha para MessagePipeline (canal-agnóstico)
    4. Envia resposta via adapter.send (mockado nos testes)
    """
    raw = await request.body()
    adapter.verify_auth(raw, dict(request.headers))
    payload = json.loads(raw) if raw else {}
    inbound = await adapter.parse_inbound(payload, dict(request.headers))

    if inbound is None:
        return StandardResponse(
            data={"received": True, "processed": False}
        )

    # Resolve pipeline do app state (populado no lifespan)
    from app.main import faq_engine, campaign_engine  # noqa: E402, WPS433
    from app.pipeline.message_pipeline import MessagePipeline  # noqa: E402

    if faq_engine is None:
        logger.error("FAQEngine não inicializado — lifespan falhou?")
        return StandardResponse(
            data={"received": True, "processed": False, "error": "not_ready"}
        )

    pipeline = MessagePipeline(
        faq_engine=faq_engine, campaign_engine=campaign_engine
    )
    outbound = await pipeline.process(inbound, db)
    db.commit()

    if outbound is None:
        # rate limit ou duplicata — respondemos 200 sem chamar Meta
        return StandardResponse(
            data={"received": True, "processed": False}
        )

    try:
        external_id = await adapter.send(outbound)
    except Exception as exc:  # noqa: BLE001 — log e segue
        logger.exception("Falha ao enviar via Meta: %s", exc)
        external_id = ""

    return StandardResponse(
        data={
            "received": True,
            "processed": True,
            "inbound_id": inbound.channel_message_id,
            "outbound_id": external_id,
        }
    )
