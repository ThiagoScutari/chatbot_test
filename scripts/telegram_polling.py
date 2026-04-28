"""Telegram long-polling — dev local only.

Não requer HTTPS nem registro de webhook na BotFather.

Uso:
    TELEGRAM_BOT_TOKEN=seu_token python scripts/telegram_polling.py

Como obter um token:
    1. Abra o Telegram e procure @BotFather
    2. Envie /newbot — siga as instruções
    3. Copie o token e adicione em .env: TELEGRAM_BOT_TOKEN=<token>

Como testar:
    1. Rode este script
    2. Abra o Telegram e envie uma mensagem para o seu bot
    3. O bot responde via FAQEngine (igual ao WhatsApp)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

# Imports após sys.path
from app.adapters.telegram import client as telegram_client  # noqa: E402
from app.adapters.telegram.adapter import TelegramAdapter  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.engines.campaign_engine import CampaignEngine  # noqa: E402
from app.engines.regex_engine import FAQEngine  # noqa: E402
from app.pipeline.message_pipeline import MessagePipeline  # noqa: E402
from app.adapters.registry import register, clear  # noqa: E402
from app.services.audio_service import AudioService  # noqa: E402


AUDIO_FALLBACK_MSG = (
    "Não consegui entender o áudio 😊 Pode repetir por favor"
)


TELEGRAM_LONGPOLL_TIMEOUT = 30
CLIENT_READ_TIMEOUT = TELEGRAM_LONGPOLL_TIMEOUT + 10  # folga para latência de rede


async def get_updates(offset: int) -> list[dict]:
    url = (
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            params={"offset": offset, "timeout": TELEGRAM_LONGPOLL_TIMEOUT},
            timeout=CLIENT_READ_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])


async def main() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN não configurado. Adicione em .env")
        return

    # ── Garante que o banco está inicializado ────────────────────────
    from app.database import engine as _engine
    from app.database_init import ensure_tables
    ensure_tables(_engine)
    logger.info("Banco de dados verificado.")

    campaign_engine = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign_engine.reload()
    faq_engine = FAQEngine(
        settings.FAQ_JSON_PATH, campaign_engine=campaign_engine
    )
    adapter = TelegramAdapter()
    # LLMRouter não é usado no polling local — latência adicional de 200-400ms
    # impacta a experiência. Habilitar apenas em produção via webhook FastAPI.
    import anthropic as _anthropic
    import json as _json
    from app.engines.context_engine import ContextEngine
    from app.engines.llm_router import LLMRouter
    _llm_config = {}
    _llm_router = None
    context_engine = None
    if settings.ANTHROPIC_API_KEY:
        _llm_config = _json.loads(
            settings.LLM_CONFIG_PATH.read_text(encoding='utf-8')
        )
        _llm_config = {k: v for k, v in _llm_config.items()
                       if not k.startswith('_')}
        _llm_client = _anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )
        _llm_router = LLMRouter(settings.LLM_CONFIG_PATH, client=_llm_client)
        _ctx_client = _anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY
        )
        context_engine = ContextEngine(
            knowledge_base_path=settings.KNOWLEDGE_BASE_PATH,
            products_path=Path("app/knowledge/products.json"),
            anthropic_client=_ctx_client,
        )
    pipeline = MessagePipeline(
        faq_engine=faq_engine,
        campaign_engine=campaign_engine,
        llm_router=_llm_router,
        llm_config=_llm_config,
        context_engine=context_engine,
    )

    audio_service: AudioService | None = None
    if settings.OPENAI_API_KEY and settings.TELEGRAM_BOT_TOKEN:
        audio_service = AudioService(
            telegram_token=settings.TELEGRAM_BOT_TOKEN,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        logger.info(
            "AudioService inicializado — transcrição de áudio ativa."
        )
    else:
        logger.info(
            "AudioService desativado — OPENAI_API_KEY não configurada."
        )

    clear()
    register(adapter)
    logger.info("Registry: adapter 'telegram' registrado.")
    logger.info(
        "Telegram polling iniciado. Envie uma mensagem para o seu bot."
    )
    offset = 0

    while True:
        try:
            updates = await get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1

                # Transcrição de áudio: se a mensagem tem voice/audio,
                # transcrevemos via Whisper e injetamos o texto em
                # update["message"]["text"] para que o adapter siga
                # o fluxo normal (canal-agnóstico).
                message = update.get("message") or {}
                voice = message.get("voice") or message.get("audio")
                if voice and not message.get("text"):
                    chat_id = message.get("chat", {}).get("id")
                    if audio_service is None:
                        logger.info(
                            "Áudio recebido mas AudioService desativado."
                        )
                        if chat_id is not None:
                            await telegram_client.send_text(
                                int(chat_id), AUDIO_FALLBACK_MSG
                            )
                        continue
                    file_id = voice.get("file_id")
                    logger.info(
                        "Áudio recebido (file_id=%s) — transcrevendo...",
                        file_id,
                    )
                    transcribed = await audio_service.transcribe(file_id)
                    if transcribed:
                        logger.info("Transcrição: %s", transcribed[:80])
                        message["text"] = transcribed
                    else:
                        if chat_id is not None:
                            await telegram_client.send_text(
                                int(chat_id), AUDIO_FALLBACK_MSG
                            )
                        continue

                inbound = await adapter.parse_inbound(update, {})
                if inbound:
                    db = SessionLocal()
                    try:
                        outbound = await pipeline.process(inbound, db)
                        if outbound:
                            await adapter.send(outbound)
                        # db.commit() é chamado dentro de pipeline.process()
                        # via check_rate_limit — não commitar novamente aqui.
                    except Exception:  # noqa: BLE001
                        logger.exception("Erro ao processar mensagem:")
                        db.rollback()
                    finally:
                        db.close()
        except httpx.ReadTimeout:
            # Long-polling expirou sem mensagens — comportamento esperado
            logger.debug("Long-poll timeout (sem mensagens), reconectando…")
        except Exception:  # noqa: BLE001
            logger.exception("Polling error — traceback completo:")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
