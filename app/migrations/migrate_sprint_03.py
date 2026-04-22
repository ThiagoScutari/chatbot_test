import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text

from app.database import engine


INDEX_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'leads' AND indexname = 'idx_leads_session_id'
    ) THEN
        CREATE INDEX idx_leads_session_id ON leads(session_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'leads' AND indexname = 'idx_leads_status'
    ) THEN
        CREATE INDEX idx_leads_status ON leads(status)
        WHERE deleted_at IS NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'leads' AND indexname = 'idx_leads_unsynced_kommo'
    ) THEN
        CREATE INDEX idx_leads_unsynced_kommo ON leads(created_at)
        WHERE synced_to_kommo_at IS NULL AND deleted_at IS NULL;
    END IF;
END $$;
"""


def migrate():
    with engine.connect() as conn:
        conn.execute(text(INDEX_SQL))
        conn.commit()
    print("OK Migration Sprint 03 aplicada - 3 indices em leads criados.")


if __name__ == "__main__":
    migrate()
