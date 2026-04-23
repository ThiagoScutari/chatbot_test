import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings


logging.basicConfig(level=settings.APP_LOG_LEVEL)
logger = logging.getLogger(__name__)

# Populated in lifespan — accessed by endpoints via module-level references
campaign_engine = None
faq_engine = None
llm_router = None
pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global campaign_engine, faq_engine, llm_router, pipeline
    import json as _json

    import anthropic as _anthropic

    from app.database import Base, engine
    from app.engines.campaign_engine import CampaignEngine
    from app.engines.llm_router import LLMRouter
    from app.engines.regex_engine import FAQEngine
    from app.pipeline.message_pipeline import MessagePipeline
    import app.models.knowledge_chunk  # noqa: F401  — registra tabela no Base.metadata

    Base.metadata.create_all(bind=engine)
    campaign_engine = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign_engine.reload()
    faq_engine = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign_engine)

    llm_config: dict = {}
    if settings.ANTHROPIC_API_KEY:
        raw = _json.loads(
            settings.LLM_CONFIG_PATH.read_text(encoding="utf-8")
        )
        llm_config = {k: v for k, v in raw.items() if not k.startswith("_")}
        client = _anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        llm_router = LLMRouter(settings.LLM_CONFIG_PATH, client=client)
        logger.info("LLMRouter inicializado — modelo: %s", llm_router.model)
    else:
        logger.info(
            "ANTHROPIC_API_KEY não configurada — "
            "LLMRouter desativado, apenas Camada 1 (FAQ regex)."
        )

    pipeline = MessagePipeline(
        faq_engine=faq_engine,
        campaign_engine=campaign_engine,
        llm_router=llm_router,
        llm_config=llm_config,
    )
    app.state.llm_router = llm_router
    app.state.pipeline = pipeline

    from app.adapters.registry import (
        clear,
        register,
        registered_channels,
    )
    from app.adapters.telegram.adapter import TelegramAdapter
    from app.adapters.whatsapp_cloud.adapter import WhatsAppCloudAdapter

    clear()  # reset on each startup
    register(WhatsAppCloudAdapter())
    if settings.TELEGRAM_BOT_TOKEN:
        register(TelegramAdapter())
        logger.info("Telegram adapter registered.")
    logger.info("Registered channels: %s", registered_channels())

    logger.info("Camisart AI started — ENV=%s", settings.APP_ENV)
    yield


app = FastAPI(title="Camisart AI", version="1.0.0", lifespan=lifespan)

from app.adapters.telegram.routes import router as telegram_router  # noqa: E402
from app.adapters.whatsapp_cloud.routes import router as whatsapp_router  # noqa: E402
from app.api.admin import router as admin_router  # noqa: E402
from app.api.health import router as health_router  # noqa: E402

app.include_router(health_router)
app.include_router(whatsapp_router)
app.include_router(telegram_router)
app.include_router(admin_router)
