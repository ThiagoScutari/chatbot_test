from pathlib import Path
from pydantic import model_validator
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
    ANTHROPIC_API_KEY: str = ""
    LLM_CONFIG_PATH: Path = Path("app/knowledge/llm_config.json")
    OPENAI_API_KEY: str = ""
    KNOWLEDGE_BASE_PATH: Path = Path("app/knowledge/camisart_knowledge_base.md")
    CONTEXT_CONFIG_PATH: Path = Path("app/knowledge/context_config.json")

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_secret_lengths(self) -> "Settings":
        if self.APP_ENV == "production":
            if len(self.ADMIN_TOKEN) < 32:
                raise ValueError(
                    "ADMIN_TOKEN deve ter pelo menos 32 caracteres em produção. "
                    "Gere com: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            if len(self.WHATSAPP_APP_SECRET) < 32:
                raise ValueError(
                    "WHATSAPP_APP_SECRET deve ter pelo menos 32 caracteres em produção."
                )
        return self


settings = Settings()
