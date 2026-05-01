"""Rollback Sprint NPS."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.migrations.migrate_sprint_nps import rollback
if __name__ == "__main__":
    rollback()
