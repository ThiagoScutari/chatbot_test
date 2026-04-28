"""Testes do AudioService — zero chamadas reais à API.

Mocks aplicados:
  - ``httpx.AsyncClient`` (chamadas getFile + download do Telegram)
  - ``openai.AsyncOpenAI`` (chamada Whisper)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audio_service import AudioService


@pytest.fixture
def service() -> AudioService:
    return AudioService(telegram_token="fake_token", openai_api_key="fake_key")


def _make_async_client(get_side_effect: list | Exception) -> MagicMock:
    """Constrói um mock de httpx.AsyncClient (context manager assíncrono).

    ``get_side_effect`` pode ser:
      - lista de respostas (uma por chamada de ``client.get``), ou
      - exceção a ser levantada na primeira chamada.
    """
    fake_client = MagicMock()
    if isinstance(get_side_effect, Exception):
        fake_client.get = AsyncMock(side_effect=get_side_effect)
    else:
        fake_client.get = AsyncMock(side_effect=get_side_effect)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_client)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    return factory


def _resp_json(payload: dict) -> MagicMock:
    r = MagicMock()
    r.json = MagicMock(return_value=payload)
    r.raise_for_status = MagicMock()
    return r


def _resp_bytes(content: bytes) -> MagicMock:
    r = MagicMock()
    r.content = content
    r.raise_for_status = MagicMock()
    return r


def _patch_openai_transcript(text: str) -> MagicMock:
    """Cria um mock para ``openai.AsyncOpenAI`` que devolve ``text``."""
    transcript = MagicMock()
    transcript.text = text

    oai_instance = MagicMock()
    oai_instance.audio = MagicMock()
    oai_instance.audio.transcriptions = MagicMock()
    oai_instance.audio.transcriptions.create = AsyncMock(return_value=transcript)

    return MagicMock(return_value=oai_instance)


async def test_transcribe_sucesso(service: AudioService) -> None:
    """Transcrição bem-sucedida retorna o texto."""
    factory = _make_async_client(
        [
            _resp_json({"result": {"file_path": "voice/file.ogg"}}),
            _resp_bytes(b"fake_audio_data"),
        ]
    )
    fake_oai = _patch_openai_transcript("qual o preço da polo?")

    with patch("app.services.audio_service.httpx.AsyncClient", factory), \
            patch("openai.AsyncOpenAI", fake_oai):
        result = await service.transcribe("file_id_123")

    assert result == "qual o preço da polo?"


async def test_transcribe_audio_vazio_retorna_none(
    service: AudioService,
) -> None:
    """Transcrição em branco retorna None."""
    factory = _make_async_client(
        [
            _resp_json({"result": {"file_path": "voice/file.ogg"}}),
            _resp_bytes(b"audio"),
        ]
    )
    fake_oai = _patch_openai_transcript("   ")

    with patch("app.services.audio_service.httpx.AsyncClient", factory), \
            patch("openai.AsyncOpenAI", fake_oai):
        result = await service.transcribe("file_id_123")

    assert result is None


async def test_transcribe_erro_api_retorna_none(
    service: AudioService,
) -> None:
    """Erro na chamada de getFile retorna None graciosamente."""
    factory = _make_async_client(Exception("API Error"))

    with patch("app.services.audio_service.httpx.AsyncClient", factory):
        result = await service.transcribe("file_id_123")

    assert result is None


async def test_transcribe_erro_download_retorna_none(
    service: AudioService,
) -> None:
    """Erro no download do .ogg retorna None."""
    bad_audio = MagicMock()
    bad_audio.raise_for_status = MagicMock(
        side_effect=Exception("Download failed")
    )

    factory = _make_async_client(
        [
            _resp_json({"result": {"file_path": "voice/file.ogg"}}),
            bad_audio,
        ]
    )

    with patch("app.services.audio_service.httpx.AsyncClient", factory):
        result = await service.transcribe("file_id_123")

    assert result is None
