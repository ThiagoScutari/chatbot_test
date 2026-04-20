import pytest
from pydantic import ValidationError


def test_short_admin_token_raises_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    monkeypatch.setenv("ADMIN_TOKEN", "short")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "x" * 32)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "token")
    with pytest.raises((ValidationError, ValueError)):
        from importlib import reload
        import app.config as cfg
        reload(cfg)
        cfg.Settings()


def test_short_secret_raises_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    monkeypatch.setenv("ADMIN_TOKEN", "x" * 32)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "short")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "token")
    with pytest.raises((ValidationError, ValueError)):
        from importlib import reload
        import app.config as cfg
        reload(cfg)
        cfg.Settings()


def test_short_tokens_allowed_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    monkeypatch.setenv("ADMIN_TOKEN", "short")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "short")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "token")
    from importlib import reload
    import app.config as cfg
    reload(cfg)
    s = cfg.Settings()
    assert s.APP_ENV == "development"
