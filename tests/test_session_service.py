from datetime import datetime, timedelta, timezone

from app.services.session_service import (
    check_rate_limit,
    get_or_create_session,
    update_state,
)


def test_creates_new_session(db):
    session, was_reset = get_or_create_session(
        db, "whatsapp_cloud", "5591111110001", "TEST_User"
    )
    assert session.channel_id == "whatsapp_cloud"
    assert was_reset is False
    assert session.current_state == "inicio"


def test_returns_existing_session(db):
    s1, _ = get_or_create_session(
        db, "whatsapp_cloud", "5591111110002", "TEST_A"
    )
    db.commit()
    s2, was_reset = get_or_create_session(
        db, "whatsapp_cloud", "5591111110002", "TEST_A"
    )
    assert s1.id == s2.id
    assert was_reset is False


def test_timeout_resets_state_preserves_nome(db):
    session, _ = get_or_create_session(
        db, "whatsapp_cloud", "5591111110003", "TEST_C"
    )
    session.current_state = "coleta_orcamento"
    session.nome_cliente = "Maria"
    session.last_interaction_at = datetime.now(timezone.utc) - timedelta(hours=3)
    db.commit()

    session2, was_reset = get_or_create_session(
        db, "whatsapp_cloud", "5591111110003", "TEST_C"
    )
    assert was_reset is True
    assert session2.current_state == "inicio"
    assert session2.nome_cliente == "Maria"


def test_rate_limit_blocks_11th_message(db):
    session, _ = get_or_create_session(
        db, "whatsapp_cloud", "5591111110004", "TEST_D"
    )
    for _ in range(10):
        assert check_rate_limit(session, db) is True
    # 11ª mensagem é bloqueada
    assert check_rate_limit(session, db) is False


def test_rate_limit_resets_after_window(db):
    session, _ = get_or_create_session(
        db, "whatsapp_cloud", "5591111110005", "TEST_E"
    )
    for _ in range(10):
        check_rate_limit(session, db)

    # Simula passagem da janela de 1 minuto
    past = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    data = dict(session.session_data or {})
    data["rl_window_start"] = past
    session.session_data = data

    assert check_rate_limit(session, db) is True


def test_rate_limit_persists_across_calls(db):
    """Counter must be visible in DB after each call."""
    session, _ = get_or_create_session(
        db, "whatsapp_cloud", "5591111110010", "TEST_RL"
    )
    check_rate_limit(session, db)
    check_rate_limit(session, db)
    # Re-fetch from DB to verify persistence
    db.expire(session)
    db.refresh(session)
    assert session.session_data.get("rl_count", 0) == 2


def test_update_state(db):
    session, _ = get_or_create_session(
        db, "whatsapp_cloud", "5591111110006", "TEST_F"
    )
    update_state(db, session, "menu")
    assert session.current_state == "menu"
