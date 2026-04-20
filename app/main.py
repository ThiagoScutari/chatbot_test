import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings


logging.basicConfig(level=settings.APP_LOG_LEVEL)
logger = logging.getLogger(__name__)

# Populated in lifespan — accessed by endpoints via module-level references
campaign_engine = None
faq_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global campaign_engine, faq_engine
    from app.database import Base, engine
    from app.engines.campaign_engine import CampaignEngine
    from app.engines.regex_engine import FAQEngine

    Base.metadata.create_all(bind=engine)
    campaign_engine = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign_engine.reload()
    faq_engine = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign_engine)
    logger.info("Camisart AI started — ENV=%s", settings.APP_ENV)
    yield


app = FastAPI(title="Camisart AI", version="1.0.0", lifespan=lifespan)

from app.api.health import router as health_router  # noqa: E402

app.include_router(health_router)
