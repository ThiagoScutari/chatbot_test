"""
Migration Sprint NPS — idempotente.
Cria tabela nps_responses para armazenar resultados das pesquisas de satisfação.

Rodar: python app/migrations/migrate_sprint_nps.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text
from app.database import engine

SQL = """
CREATE TABLE IF NOT EXISTS nps_responses (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id        BIGINT NOT NULL,
    nome                    TEXT NOT NULL,
    nota_logistica          INTEGER CHECK (nota_logistica BETWEEN 0 AND 10),
    nota_produto_qualidade  INTEGER CHECK (nota_produto_qualidade BETWEEN 0 AND 10),
    nota_produto_expectativa INTEGER CHECK (nota_produto_expectativa BETWEEN 0 AND 10),
    nota_atendimento        INTEGER CHECK (nota_atendimento BETWEEN 0 AND 10),
    nota_indicacao          INTEGER CHECK (nota_indicacao BETWEEN 0 AND 10),
    comentario              TEXT,
    media_geral             NUMERIC(4,2),
    nps_classificacao       TEXT CHECK (nps_classificacao IN ('promotor', 'neutro', 'detrator')),
    raw_data                JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nps_classificacao
    ON nps_responses (nps_classificacao);

CREATE INDEX IF NOT EXISTS idx_nps_created_at
    ON nps_responses (created_at DESC);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS nps_responses CASCADE;
"""

def migrate():
    with engine.connect() as conn:
        conn.execute(text(SQL))
        conn.commit()
    print("✅ Migration NPS aplicada — tabela nps_responses criada.")

def rollback():
    confirm = input("Remove tabela nps_responses. Digite 'CONFIRMAR': ")
    if confirm == "CONFIRMAR":
        with engine.connect() as conn:
            conn.execute(text(ROLLBACK_SQL))
            conn.commit()
        print("✅ Rollback NPS executado.")
    else:
        print("Cancelado.")

if __name__ == "__main__":
    migrate()
