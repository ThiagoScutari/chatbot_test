"""ConversationSimulator — cliente de testes de alto nível.

Simula um usuário conversando com o bot via MessagePipeline real,
sem Telegram e sem HTTP. Mesma sessão entre mensagens, igual a um
usuário real.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.pipeline.message_pipeline import MessagePipeline
from app.schemas.messaging import InboundMessage, OutboundMessage


class ConversationSimulator:
    """Simula uma conversa completa via MessagePipeline."""

    def __init__(
        self,
        pipeline: MessagePipeline,
        db: Session,
        channel_id: str = "telegram",
        user_id: str | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.db = db
        self.channel_id = channel_id
        self.user_id = user_id or f"TEST_SIM_{uuid.uuid4().hex[:8]}"
        self.message_counter = 0
        self._last_outbound: OutboundMessage | None = None
        self._sent_messages: list[OutboundMessage] = []

    async def send(self, text: str) -> OutboundMessage | None:
        """Envia uma mensagem e retorna o OutboundMessage de resposta."""
        self.message_counter += 1
        inbound = InboundMessage(
            channel_id=self.channel_id,
            channel_message_id=f"sim_{self.user_id}_{self.message_counter}",
            channel_user_id=self.user_id,
            display_name="TEST_Simulador",
            content=text,
            timestamp=datetime.now(timezone.utc),
            raw_payload={"simulated": True, "text": text},
        )
        outbound = await self.pipeline.process(inbound, self.db)
        self._last_outbound = outbound
        if outbound:
            self._sent_messages.append(outbound)
        return outbound

    @property
    def last_response(self) -> str:
        if not self._last_outbound:
            return ""
        return self._last_outbound.response.get("body", "")

    @property
    def last_response_type(self) -> str:
        if not self._last_outbound:
            return ""
        return self._last_outbound.response.get("type", "text")

    @property
    def last_buttons(self) -> list[dict]:
        if not self._last_outbound:
            return []
        return self._last_outbound.response.get("buttons", []) or []

    def _session(self):
        from app.models.session import Session as SessionModel

        return (
            self.db.query(SessionModel)
            .filter_by(
                channel_id=self.channel_id,
                channel_user_id=self.user_id,
            )
            .first()
        )

    @property
    def state(self) -> str:
        session = self._session()
        return session.current_state if session else "unknown"

    @property
    def session_data(self) -> dict:
        session = self._session()
        return session.session_data if session else {}

    @property
    def nome_cliente(self) -> str | None:
        session = self._session()
        return session.nome_cliente if session else None

    def last_text_contains(self, substring: str) -> bool:
        return substring.lower() in self.last_response.lower()

    def history(self) -> list[str]:
        """Textos de todas as respostas — inclui títulos de botões/list items."""
        result = []
        for m in self._sent_messages:
            body = m.response.get("body", "")
            buttons = m.response.get("buttons") or []
            list_items = m.response.get("list_items") or []
            extras = [b.get("title", "") for b in buttons] + [
                it.get("title", "") for it in list_items
            ]
            if extras:
                body = body + " " + " ".join(extras)
            result.append(body)
        return result

    def reset_rate_limit(self) -> None:
        """Reseta contador de rate limit — uso exclusivo em testes."""
        session = self._session()
        if session is None:
            return
        data = dict(session.session_data or {})
        data.pop("rl_window_start", None)
        data.pop("rl_count", None)
        session.session_data = data
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(session, "session_data")
        self.db.flush()

    def leads_captured(self) -> list:
        from app.models.lead import Lead

        session = self._session()
        if not session:
            return []
        return self.db.query(Lead).filter_by(session_id=session.id).all()
