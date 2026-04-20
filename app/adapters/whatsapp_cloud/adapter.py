"""WhatsAppCloudAdapter — implementação do ChannelAdapter para Meta Cloud API."""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.adapters.base import ChannelAdapter
from app.adapters.whatsapp_cloud import client
from app.config import settings
from app.schemas.messaging import InboundMessage, OutboundMessage


logger = logging.getLogger(__name__)


class WhatsAppCloudAdapter(ChannelAdapter):
    """Adapter para o canal WhatsApp Cloud API oficial da Meta."""

    channel_id = "whatsapp_cloud"

    def verify_auth(
        self, raw_payload: bytes, headers: dict[str, str]
    ) -> None:
        """Valida assinatura HMAC-SHA256 da Meta via WHATSAPP_APP_SECRET.

        Levanta HTTPException(403) se a assinatura estiver ausente ou inválida.
        Headers são normalizados para lowercase por FastAPI.
        """
        norm_headers = {k.lower(): v for k, v in headers.items()}
        signature = norm_headers.get("x-hub-signature-256", "")
        if not signature or not signature.startswith("sha256="):
            raise HTTPException(status_code=403, detail="Signature missing.")
        expected = (
            "sha256="
            + hmac.new(
                settings.WHATSAPP_APP_SECRET.encode(),
                raw_payload,
                hashlib.sha256,
            ).hexdigest()
        )
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=403, detail="Signature invalid.")

    async def parse_inbound(
        self, raw_payload: dict[str, Any], headers: dict[str, str]
    ) -> InboundMessage | None:
        """Extrai a primeira mensagem de texto/interactive do payload da Meta.

        Retorna None para status updates (delivered/read/sent).
        """
        try:
            entry = (raw_payload.get("entry") or [])[0]
            change = (entry.get("changes") or [])[0]
            value = change.get("value", {})
        except (IndexError, AttributeError):
            return None

        # Status updates não viram InboundMessage
        if value.get("statuses") and not value.get("messages"):
            return None

        messages = value.get("messages") or []
        if not messages:
            return None

        msg = messages[0]
        msg_id = msg.get("id", "")
        wa_user = msg.get("from", "")
        msg_type = msg.get("type", "")
        ts_raw = msg.get("timestamp", "")
        try:
            ts = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        except (TypeError, ValueError):
            ts = datetime.now(timezone.utc)

        # Extrai conteúdo de acordo com o tipo
        content: str | None = None
        if msg_type == "text":
            content = (msg.get("text") or {}).get("body")
        elif msg_type == "interactive":
            interactive = msg.get("interactive") or {}
            i_type = interactive.get("type")
            if i_type == "button_reply":
                content = (interactive.get("button_reply") or {}).get("id")
            elif i_type == "list_reply":
                content = (interactive.get("list_reply") or {}).get("id")

        if not content:
            # Tipo não suportado na Fase 1 (image/audio/video/document/location)
            logger.info(
                "Mensagem tipo '%s' ignorada na Fase 1 (id=%s)", msg_type, msg_id
            )
            return None

        # Nome do contato, se disponível
        display_name: str | None = None
        contacts = value.get("contacts") or []
        if contacts:
            profile = (contacts[0] or {}).get("profile") or {}
            display_name = profile.get("name")

        return InboundMessage(
            channel_id="whatsapp_cloud",
            channel_message_id=msg_id,
            channel_user_id=wa_user,
            display_name=display_name,
            content=content,
            timestamp=ts,
            raw_payload=raw_payload,
        )

    def _build_meta_payload(self, outbound: OutboundMessage) -> dict:
        response = outbound.response
        r_type = response.get("type", "text")
        to = outbound.channel_user_id

        if r_type == "buttons" and response.get("buttons"):
            interactive: dict[str, Any] = {
                "type": "button",
                "body": {"text": response["body"]},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": b["id"], "title": b["title"][:20]},
                        }
                        for b in response["buttons"][:3]
                    ]
                },
            }
            if response.get("footer"):
                interactive["footer"] = {"text": response["footer"]}
            return {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": interactive,
            }

        if r_type == "list" and response.get("list_items"):
            return {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": response["body"]},
                    "action": {
                        "button": response.get("list_button_label", "Ver opções")[:20],
                        "sections": [
                            {
                                "rows": [
                                    {
                                        "id": item["id"],
                                        "title": item["title"][:24],
                                        **(
                                            {"description": item["description"][:72]}
                                            if item.get("description")
                                            else {}
                                        ),
                                    }
                                    for item in response["list_items"][:10]
                                ]
                            }
                        ],
                    },
                },
            }

        return {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": response.get("body", "")},
        }

    async def send(self, outbound: OutboundMessage) -> str:
        """Converte OutboundMessage em payload da Meta e envia via client."""
        payload = self._build_meta_payload(outbound)
        return await client.send_message(
            settings.WHATSAPP_PHONE_NUMBER_ID, payload
        )
