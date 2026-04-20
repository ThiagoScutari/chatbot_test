"""Cliente HTTP para a Telegram Bot API.

Mockado em todos os testes — NUNCA chamar a API real em teste.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


async def send_text(chat_id: int, text: str) -> str:
    """Envia texto simples para um chat. Retorna message_id como str."""
    url = (
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10.0,
        )
        resp.raise_for_status()
        result = resp.json()
        return str(result["result"]["message_id"])
