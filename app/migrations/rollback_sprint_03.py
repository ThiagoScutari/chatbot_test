import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text

from app.database import engine


def rollback():
    confirm = input("Remove indices Sprint 03. Digite 'CONFIRMAR': ")
    if confirm == "CONFIRMAR":
        with engine.connect() as conn:
            conn.execute(text("DROP INDEX IF EXISTS idx_leads_session_id;"))
            conn.execute(text("DROP INDEX IF EXISTS idx_leads_status;"))
            conn.execute(text("DROP INDEX IF EXISTS idx_leads_unsynced_kommo;"))
            conn.commit()
        print("OK Rollback Sprint 03 executado.")
    else:
        print("Cancelado.")


if __name__ == "__main__":
    rollback()
