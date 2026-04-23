import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:test@localhost:5432/camisart_test_db",
)
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql://postgres:test@localhost:5432/camisart_test_db",
)
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("WHATSAPP_APP_SECRET", "test-app-secret-32-chars-minimum-ok")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token-32-chars-minimum-ok")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-fake-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "test-fake-openai-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app

# Import models para registrá-los no Base.metadata
import app.models.session  # noqa: F401
import app.models.message  # noqa: F401
import app.models.lead  # noqa: F401
import app.models.audit_log  # noqa: F401
# knowledge_chunk NÃO é importado aqui — requer extensão pgvector no banco.
# Testes RAG mocam a sessão de DB, então a tabela não precisa existir no teste.


TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
test_engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sessions_updated_at'
    ) THEN
        CREATE TRIGGER trg_sessions_updated_at
        BEFORE UPDATE ON sessions
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_leads_updated_at'
    ) THEN
        CREATE TRIGGER trg_leads_updated_at
        BEFORE UPDATE ON leads
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;
"""


_INDEX_SQL = """
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


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    from sqlalchemy import text

    Base.metadata.create_all(bind=test_engine)
    with test_engine.connect() as conn:
        conn.execute(text(_TRIGGER_SQL))
        conn.execute(text(_INDEX_SQL))
        conn.commit()
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    """TestClient com override do get_db, engines e registry inicializados.

    Inicializa CampaignEngine, FAQEngine e registra os adapters
    manualmente (sem usar o lifespan para não recriar o schema no banco
    de teste a cada fixture).
    """
    from pathlib import Path

    import app.main as app_main
    from app.adapters.registry import clear, register
    from app.adapters.telegram.adapter import TelegramAdapter
    from app.adapters.whatsapp_cloud.adapter import WhatsAppCloudAdapter
    from app.engines.campaign_engine import CampaignEngine
    from app.engines.regex_engine import FAQEngine

    # Setup engines (idempotente — mesmos objetos em execuções paralelas)
    campaign_engine = CampaignEngine(Path("app/knowledge/campaigns.json"))
    campaign_engine.reload()
    faq_engine = FAQEngine(
        Path("app/knowledge/faq.json"), campaign_engine=campaign_engine
    )
    app_main.campaign_engine = campaign_engine
    app_main.faq_engine = faq_engine

    # Setup registry para que pipeline.send_catalog resolva adapter por canal
    clear()
    register(WhatsAppCloudAdapter())
    register(TelegramAdapter())

    def override_get_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    # TestClient sem context manager para NÃO disparar o lifespan
    # (que rodaria Base.metadata.create_all no banco de produção).
    c = TestClient(fastapi_app)
    try:
        yield c
    finally:
        fastapi_app.dependency_overrides.clear()
        clear()


@pytest.fixture
def pipeline(db):
    """MessagePipeline com FAQEngine e CampaignEngine reais."""
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql://postgres:test@localhost:5432/camisart_test_db",
    )
    from app.config import settings
    from app.engines.campaign_engine import CampaignEngine
    from app.engines.regex_engine import FAQEngine
    from app.pipeline.message_pipeline import MessagePipeline

    campaign = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign.reload()
    faq = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign)
    return MessagePipeline(
        faq_engine=faq,
        campaign_engine=campaign,
        llm_router=None,  # testes usam apenas Camada 1 por padrão
        rag_engine=None,  # testes usam apenas Camadas 1 e 2
    )


@pytest.fixture
def sim(pipeline, db):
    """ConversationSimulator pronto para uso com user_id único."""
    import uuid

    from tests.helpers.conversation_simulator import ConversationSimulator

    return ConversationSimulator(
        pipeline, db, user_id=f"TEST_SIM_{uuid.uuid4().hex[:8]}"
    )
