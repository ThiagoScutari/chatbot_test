import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text

from app.database import engine


def rollback():
    confirm = input("Remove triggers set_updated_at. Digite 'CONFIRMAR': ")
    if confirm == "CONFIRMAR":
        with engine.connect() as conn:
            conn.execute(text("DROP TRIGGER IF EXISTS trg_sessions_updated_at ON sessions;"))
            conn.execute(text("DROP TRIGGER IF EXISTS trg_leads_updated_at ON leads;"))
            conn.commit()
        print("OK Rollback Sprint 02 executado.")
    else:
        print("Cancelado.")


if __name__ == "__main__":
    rollback()
