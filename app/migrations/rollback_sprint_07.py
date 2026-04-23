import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text

from app.database import engine


def rollback():
    confirm = input(
        "Remove knowledge_chunks e desativa vector. Digite 'CONFIRMAR': "
    )
    if confirm == "CONFIRMAR":
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS knowledge_chunks CASCADE;"))
            conn.commit()
        print("OK Rollback Sprint 07 executado.")
    else:
        print("Cancelado.")


if __name__ == "__main__":
    rollback()
