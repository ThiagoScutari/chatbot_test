"""Migration Sprint 01 — idempotente. Cria tabelas via SQLAlchemy.

Rodar: python app/migrations/migrate_sprint_01.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import Base, engine  # noqa: E402
import app.models.session  # noqa: F401, E402
import app.models.message  # noqa: F401, E402
import app.models.lead  # noqa: F401, E402
import app.models.audit_log  # noqa: F401, E402


def migrate() -> None:
    """Cria tabelas do Sprint 01. Idempotente — pode rodar várias vezes."""
    Base.metadata.create_all(bind=engine)
    print("✅ Migration Sprint 01 aplicada.")


if __name__ == "__main__":
    migrate()
