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
from app.main import app


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
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
