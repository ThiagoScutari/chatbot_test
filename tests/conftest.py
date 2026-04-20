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


TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
test_engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
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
    """TestClient com override do get_db e engines inicializados.

    Inicializa CampaignEngine e FAQEngine manualmente (sem usar o lifespan
    para não recriar o schema no banco de teste a cada fixture).
    """
    from pathlib import Path

    import app.main as app_main
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
