"""
Inicialização do banco de dados — cria todas as tabelas
se ainda não existirem. Idempotente: seguro rodar múltiplas vezes.

Usado por:
  - scripts/telegram_polling.py (desenvolvimento local)
  - app/main.py lifespan (produção via FastAPI)
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def ensure_tables(engine) -> None:
    """
    Garante que todas as tabelas existem no banco.
    Usa create_all(checkfirst=True) — nunca destrói dados existentes.
    Também ativa a extensão pgvector se disponível.
    """
    from app.database import Base

    # Importar todos os models para que Base.metadata os conheça
    import app.models.session  # noqa: F401
    import app.models.message  # noqa: F401
    import app.models.lead  # noqa: F401
    import app.models.audit_log  # noqa: F401

    # Ativar pgvector (necessário para knowledge_chunks)
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            logger.debug("pgvector: extensão verificada.")
        except Exception:  # noqa: BLE001
            conn.rollback()
            logger.debug("pgvector: extensão não disponível (ignorado).")

    # Criar tabela knowledge_chunks manualmente se necessário —
    # SQLAlchemy não consegue criar a coluna `vector` antes da extensão
    # estar ativa em pools paralelos.
    with engine.connect() as conn:
        inspector = inspect(engine)
        existing = inspector.get_table_names()

        if "knowledge_chunks" not in existing:
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS knowledge_chunks (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        source VARCHAR(256) NOT NULL,
                        chunk_id VARCHAR(256) NOT NULL,
                        content TEXT NOT NULL,
                        embedding vector(1536),
                        metadata JSONB NOT NULL DEFAULT '{}',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        CONSTRAINT uq_knowledge_chunk UNIQUE (source, chunk_id)
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS knowledge_chunks_hnsw_idx
                    ON knowledge_chunks
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                """))
                conn.commit()
                logger.info("knowledge_chunks: tabela criada.")
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                logger.warning(
                    "knowledge_chunks: não foi possível criar (%s)", e
                )

    # Criar todas as outras tabelas via SQLAlchemy
    Base.metadata.create_all(engine, checkfirst=True)

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    logger.info("Banco inicializado. Tabelas: %s", ", ".join(sorted(tables)))
