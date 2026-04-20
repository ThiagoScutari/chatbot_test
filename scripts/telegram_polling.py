"""Telegram long-polling — dev local only.

Não requer HTTPS nem registro de webhook na BotFather.

Uso:
    TELEGRAM_BOT_TOKEN=seu_token python scripts/telegram_polling.py

Como obter um token:
    1. Abra o Telegram e procure @BotFather
    2. Envie /newbot — siga as instruções
    3. Copie o token e adicione em .env: TELEGRAM_BOT_TOKEN=<token>

Como testar:
    1. Rode este script
    2. Abra o Telegram e envie uma mensagem para o seu bot
    3. O bot responde via FAQEngine (igual ao WhatsApp)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

# Imports após sys.path
from app.adapters.telegram.adapter import TelegramAdapter  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.engines.campaign_engine import CampaignEngine  # noqa: E402
from app.engines.regex_engine import FAQEngine  # noqa: E402
from app.pipeline.message_pipeline import MessagePipeline  # noqa: E402


async def get_updates(offset: int) -> list[dict]:
    url = (
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            params={"offset": offset, "timeout": 30},
            timeout=35.0,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])


async def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN não configurado. Adicione em .env")
        return

    campaign_engine = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign_engine.reload()
    faq_engine = FAQEngine(
        settings.FAQ_JSON_PATH, campaign_engine=campaign_engine
    )
    adapter = TelegramAdapter()
    pipeline = MessagePipeline(
        faq_engine=faq_engine, campaign_engine=campaign_engine
    )

    logger.info(
        "Telegram polling iniciado. Envie uma mensagem para o seu bot."
    )
    offset = 0

    while True:
        try:
            updates = await get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                inbound = await adapter.parse_inbound(update, {})
                if inbound:
                    db = SessionLocal()
                    try:
                        outbound = await pipeline.process(inbound, db)
                        db.commit()
                        if outbound:
                            await adapter.send(outbound)
                    finally:
                        db.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("Polling error: %s", exc)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
