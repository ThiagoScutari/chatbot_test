from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_LOG_LEVEL: str = "INFO"
    DATABASE_URL: str
    TEST_DATABASE_URL: str = ""
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "dev-verify-token"
    WHATSAPP_APP_SECRET: str = "dev-secret-32-chars-minimum-paddd"
    WHATSAPP_API_VERSION: str = "v20.0"
    ADMIN_TOKEN: str = "dev-admin-token-32-chars-minimum-"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    FAQ_JSON_PATH: Path = Path("app/knowledge/faq.json")
    CAMPAIGNS_JSON_PATH: Path = Path("app/knowledge/campaigns.json")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
