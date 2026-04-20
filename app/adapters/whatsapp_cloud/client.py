"""Cliente HTTP para a Meta Graph API (WhatsApp Cloud)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings


logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com"


async def send_message(phone_number_id: str, payload: dict[str, Any]) -> str:
    """Envia uma mensagem via Meta Graph API.

    Retorna o `wamid` gerado pela Meta. Nos testes, esta função é mockada
    via `unittest.mock.patch` — NUNCA chamar a API real em testes.
    """
    url = (
        f"{GRAPH_URL}/{settings.WHATSAPP_API_VERSION}/"
        f"{phone_number_id}/messages"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("messages", [])
        if messages:
            return messages[0].get("id", "")
        logger.warning("Meta API retornou sem 'messages': %s", data)
        return ""
