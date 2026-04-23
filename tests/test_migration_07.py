import pytest
from sqlalchemy import text

from app.database import engine


@pytest.fixture(scope="module", autouse=True)
def _run_migration():
    """Executa a migration antes dos testes de índices — cria HNSW e idx_source.

    create_all do SQLAlchemy cria a tabela mas não os índices pgvector raw SQL.
    """
    from app.migrations.migrate_sprint_07 import migrate

    migrate()


def test_pgvector_extension_habilitada():
    """Extensão vector deve estar disponível no banco de teste."""
    with engine.connect() as conn:
        r = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        ).fetchone()
    assert r is not None, (
        "extensão pgvector não habilitada — instalar "
        "postgresql-15-pgvector no banco"
    )


def test_knowledge_chunks_table_exists():
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name='knowledge_chunks'"
            )
        ).fetchone()
    assert r is not None, "tabela knowledge_chunks não existe"


def test_hnsw_index_exists():
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename='knowledge_chunks' "
                "AND indexname='idx_knowledge_chunks_embedding'"
            )
        ).fetchone()
    assert r is not None, "índice HNSW idx_knowledge_chunks_embedding não encontrado"


def test_source_index_exists():
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename='knowledge_chunks' "
                "AND indexname='idx_knowledge_chunks_source'"
            )
        ).fetchone()
    assert r is not None, "índice idx_knowledge_chunks_source não encontrado"


def test_migration_idempotent():
    """Rodar duas vezes não levanta erro."""
    from app.migrations.migrate_sprint_07 import migrate

    migrate()
    migrate()  # segunda execução — todos os objetos com IF NOT EXISTS
