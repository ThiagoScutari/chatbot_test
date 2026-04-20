"""ChannelAdapter ABC — contrato único de todo canal externo.

Toda classe concreta (WhatsAppCloudAdapter, KommoAdapter, …) deve implementar
este contrato. O cérebro do bot (pipeline, engines, services) só conhece
`InboundMessage` e `OutboundMessage` — nunca detalhes do canal.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.messaging import InboundMessage, OutboundMessage


class ChannelAdapter(ABC):
    """Contrato único que todo canal deve implementar."""

    channel_id: str  # 'whatsapp_cloud', 'kommo', 'instagram_dm', ...

    @abstractmethod
    async def parse_inbound(
        self, raw_payload: dict[str, Any], headers: dict[str, str]
    ) -> InboundMessage | None:
        """Converte payload do canal em mensagem canônica.

        Retorna None quando o payload é apenas um status update
        (delivered, read, sent) que não requer processamento.
        """

    @abstractmethod
    async def send(self, outbound: OutboundMessage) -> str:
        """Envia mensagem pelo canal. Retorna o id externo gerado."""

    @abstractmethod
    def verify_auth(
        self, raw_payload: bytes, headers: dict[str, str]
    ) -> None:
        """Valida HMAC/token do canal. Levanta HTTPException(403) se inválido."""
