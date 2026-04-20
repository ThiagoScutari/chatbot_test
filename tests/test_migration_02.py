import time

from sqlalchemy import text

from app.database import engine


def test_trigger_sessions_exists():
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sessions_updated_at'")
        ).fetchone()
    assert result is not None, "Trigger trg_sessions_updated_at não encontrado"


def test_trigger_leads_exists():
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pg_trigger WHERE tgname = 'trg_leads_updated_at'")
        ).fetchone()
    assert result is not None, "Trigger trg_leads_updated_at não encontrado"


def test_sessions_updated_at_changes_on_raw_sql(db):
    from app.models.session import Session as SessionModel

    s = SessionModel(channel_id="whatsapp_cloud", channel_user_id="TEST_trigger_001")
    db.add(s)
    db.flush()
    original_updated = s.updated_at
    time.sleep(0.05)
    db.execute(
        text("UPDATE sessions SET nome_cliente = 'trigger_test' WHERE id = :id"),
        {"id": str(s.id)},
    )
    db.flush()
    db.expire(s)
    db.refresh(s)
    assert s.updated_at > original_updated, (
        "updated_at não mudou após UPDATE raw SQL — trigger não está ativo"
    )
