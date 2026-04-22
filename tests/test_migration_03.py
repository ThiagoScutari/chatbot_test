from sqlalchemy import text

from app.database import engine


def test_index_session_id_exists():
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename='leads' AND indexname='idx_leads_session_id'"
            )
        ).fetchone()
    assert r is not None, "idx_leads_session_id nao encontrado"


def test_index_status_exists():
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename='leads' AND indexname='idx_leads_status'"
            )
        ).fetchone()
    assert r is not None, "idx_leads_status nao encontrado"


def test_index_unsynced_kommo_exists():
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename='leads' AND indexname='idx_leads_unsynced_kommo'"
            )
        ).fetchone()
    assert r is not None, "idx_leads_unsynced_kommo nao encontrado"


def test_migration_idempotent():
    """Rodar duas vezes nao levanta erro."""
    from app.migrations.migrate_sprint_03 import migrate

    migrate()
