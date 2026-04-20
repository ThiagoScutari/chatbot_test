"""Endpoints FastAPI do adapter Telegram (webhook mode).

Para long-polling local sem HTTPS, usar `scripts/telegram_polling.py`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.adapters.telegram.adapter import TelegramAdapter
from app.schemas.response import StandardResponse


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/adapters/telegram", tags=["telegram"])
adapter = TelegramAdapter()


@router.post("/webhook", status_code=200)
async def receive_telegram(request: Request) -> StandardResponse:
    raw = await request.body()
    adapter.verify_auth(raw, dict(request.headers))
    payload = await request.json()
    inbound = await adapter.parse_inbound(payload, dict(request.headers))

    # Pipeline wiring: mesmo padrão do WhatsApp adapter
    from app.main import campaign_engine, faq_engine  # noqa: WPS433

    if inbound and faq_engine:
        from app.database import SessionLocal  # noqa: WPS433
        from app.pipeline.message_pipeline import MessagePipeline  # noqa: WPS433

        db = SessionLocal()
        try:
            pipeline = MessagePipeline(
                faq_engine=faq_engine, campaign_engine=campaign_engine
            )
            outbound = await pipeline.process(inbound, db)
            db.commit()
            if outbound:
                try:
                    await adapter.send(outbound)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Falha ao enviar via Telegram: %s", exc)
        finally:
            db.close()

    return StandardResponse(data={"received": True})
