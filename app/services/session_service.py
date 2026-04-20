"""SessionService — persistência de sessões com timeout e rate limit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.session import Session as SessionModel


SESSION_TIMEOUT_HOURS = 2
RATE_LIMIT_WINDOW = timedelta(minutes=1)
RATE_LIMIT_MAX_MSGS = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_session(
    db: Session,
    channel_id: str,
    channel_user_id: str,
    display_name: str | None = None,
) -> tuple[SessionModel, bool]:
    """Retorna (session, was_reset).

    Cria sessão nova se não existir.
    Se existir e `last_interaction_at` for mais antigo que SESSION_TIMEOUT,
    reseta current_state='inicio' e limpa session_data, preservando
    `nome_cliente`. was_reset=True nesse caso.
    """
    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.channel_id == channel_id,
            SessionModel.channel_user_id == channel_user_id,
            SessionModel.deleted_at.is_(None),
        )
        .first()
    )

    if session is None:
        session = SessionModel(
            channel_id=channel_id,
            channel_user_id=channel_user_id,
            display_name=display_name,
        )
        db.add(session)
        db.flush()
        return session, False

    last = session.last_interaction_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is not None and _now() - last > timedelta(hours=SESSION_TIMEOUT_HOURS):
        nome_salvo = session.nome_cliente
        session.current_state = "inicio"
        session.session_data = {}
        session.nome_cliente = nome_salvo
        session.last_interaction_at = _now()
        db.flush()
        return session, True

    return session, False


def check_rate_limit(session: SessionModel) -> bool:
    """Rate limit por `channel_user_id`: `RATE_LIMIT_MAX_MSGS`/min via session_data.

    Retorna True se permitido, False se excedeu.
    """
    now = _now()
    data = dict(session.session_data or {})
    window_start_iso = data.get("rl_window_start")

    if window_start_iso is None:
        data["rl_window_start"] = now.isoformat()
        data["rl_count"] = 1
        session.session_data = data
        return True

    try:
        window_start = datetime.fromisoformat(window_start_iso)
    except (TypeError, ValueError):
        window_start = now

    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)

    if now - window_start > RATE_LIMIT_WINDOW:
        # Nova janela
        data["rl_window_start"] = now.isoformat()
        data["rl_count"] = 1
        session.session_data = data
        return True

    count = int(data.get("rl_count", 0)) + 1
    data["rl_count"] = count
    session.session_data = data
    return count <= RATE_LIMIT_MAX_MSGS


def update_state(
    db: Session, session: SessionModel, new_state: str
) -> None:
    """Atualiza o estado atual e o timestamp de última interação."""
    session.current_state = new_state
    session.last_interaction_at = _now()
    db.flush()
