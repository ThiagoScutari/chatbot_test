"""Rollback Sprint 01 — DROP todas as tabelas criadas neste sprint.

Uso interativo: python app/migrations/rollback_sprint_01.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import Base, engine  # noqa: E402
import app.models.session  # noqa: F401, E402
import app.models.message  # noqa: F401, E402
import app.models.lead  # noqa: F401, E402
import app.models.audit_log  # noqa: F401, E402


def rollback() -> None:
    confirm = input(
        "Isso apagará TODOS os dados. Digite 'CONFIRMAR' para prosseguir: "
    )
    if confirm == "CONFIRMAR":
        Base.metadata.drop_all(bind=engine)
        print("✅ Rollback Sprint 01 executado.")
    else:
        print("Cancelado.")


if __name__ == "__main__":
    rollback()
