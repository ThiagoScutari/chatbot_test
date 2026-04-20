"""TelegramAdapter — implementação do ChannelAdapter para Telegram Bot API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.adapters.base import ChannelAdapter
from app.adapters.telegram import client
from app.adapters.telegram.schemas import TelegramUpdate
from app.config import settings
from app.schemas.messaging import InboundMessage, OutboundMessage


logger = logging.getLogger(__name__)


class TelegramAdapter(ChannelAdapter):
    """Adapter para o canal Telegram Bot API."""

    channel_id = "telegram"

    async def parse_inbound(
        self, raw_payload: dict[str, Any], headers: dict[str, str]
    ) -> InboundMessage | None:
        """Converte update do Telegram em InboundMessage canônica.

        Retorna None para updates não-texto (sticker, foto, edited_message,
        channel_post, etc.) — Fase 1 só processa texto.
        """
        try:
            update = TelegramUpdate(**raw_payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Payload Telegram não-parseável: %s", exc)
            return None

        if not update.message or not update.message.text:
            return None

        msg = update.message
        return InboundMessage(
            channel_id="telegram",
            channel_message_id=str(msg.message_id),
            channel_user_id=str(msg.chat.id),
            display_name=msg.from_user.first_name if msg.from_user else None,
            content=msg.text,
            timestamp=datetime.fromtimestamp(msg.date, tz=timezone.utc),
            raw_payload=raw_payload,
        )

    async def send(self, outbound: OutboundMessage) -> str:
        """Envia texto para o chat do Telegram.

        Converte botões (`type: "buttons"`) em opções numeradas no corpo —
        modo básico sem inline keyboard na Fase 1.
        """
        body = outbound.response.get("body", "")
        buttons = outbound.response.get("buttons")
        if buttons:
            options = "\n".join(
                f"{i + 1}. {b['title']}" for i, b in enumerate(buttons)
            )
            body = f"{body}\n\n{options}"
        return await client.send_text(int(outbound.channel_user_id), body)

    def verify_auth(
        self, raw_payload: bytes, headers: dict[str, str]
    ) -> None:
        """Valida header `X-Telegram-Bot-Api-Secret-Token`.

        Se `TELEGRAM_WEBHOOK_SECRET` está vazio (dev/local), valida skip.
        Em produção, o secret é configurado ao registrar o webhook
        (`setWebhook?secret_token=...`) e o Telegram envia no header.
        """
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        if not secret:
            return
        norm_headers = {k.lower(): v for k, v in headers.items()}
        token_header = norm_headers.get(
            "x-telegram-bot-api-secret-token", ""
        )
        if token_header != secret:
            raise HTTPException(
                status_code=403, detail="Invalid Telegram secret token."
            )
