"""AudioService — transcreve mensagens de áudio do Telegram via Whisper API.

Fluxo:
  1. Recebe ``file_id`` do Telegram
  2. Baixa o arquivo .ogg via Telegram Bot API (getFile + download)
  3. Envia para Whisper (modelo whisper-1, PT-BR)
  4. Retorna texto transcrito (ou ``None`` em qualquer falha)

Custo: ~$0.006/min (áudio de 30s ≈ $0.003).
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

WHISPER_MODEL = "whisper-1"
TELEGRAM_GET_FILE = "https://api.telegram.org/bot{token}/getFile"
TELEGRAM_FILE_URL = "https://api.telegram.org/file/bot{token}/{file_path}"


class AudioService:
    def __init__(self, telegram_token: str, openai_api_key: str) -> None:
        self._token = telegram_token
        self._openai_key = openai_api_key

    async def transcribe(self, file_id: str) -> str | None:
        """Baixa e transcreve um áudio do Telegram.

        Retorna o texto transcrito ou ``None`` em qualquer falha
        (rede, API, payload inesperado, transcrição vazia).
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    TELEGRAM_GET_FILE.format(token=self._token),
                    params={"file_id": file_id},
                )
                resp.raise_for_status()
                file_path = resp.json()["result"]["file_path"]

            file_url = TELEGRAM_FILE_URL.format(
                token=self._token,
                file_path=file_path,
            )
            async with httpx.AsyncClient(timeout=30.0) as client:
                audio_resp = await client.get(file_url)
                audio_resp.raise_for_status()
                audio_bytes = audio_resp.content

            import openai
            oai_client = openai.AsyncOpenAI(api_key=self._openai_key)

            with tempfile.NamedTemporaryFile(
                suffix=".ogg", delete=False
            ) as tmp:
                tmp.write(audio_bytes)
                tmp_path = Path(tmp.name)

            try:
                with open(tmp_path, "rb") as audio_file:
                    transcript = await oai_client.audio.transcriptions.create(
                        model=WHISPER_MODEL,
                        file=audio_file,
                        language="pt",
                        response_format="text",
                    )
                text = (
                    transcript.strip()
                    if isinstance(transcript, str)
                    else transcript.text.strip()
                )
                logger.info(
                    "Áudio transcrito (%d chars): %s",
                    len(text),
                    text[:60],
                )
                return text if text else None
            finally:
                tmp_path.unlink(missing_ok=True)

        except Exception as exc:  # noqa: BLE001
            logger.error("AudioService.transcribe erro: %s", exc)
            return None
