import pytest

from app.adapters.registry import clear, get, register, registered_channels
from app.adapters.telegram.adapter import TelegramAdapter
from app.adapters.whatsapp_cloud.adapter import WhatsAppCloudAdapter


@pytest.fixture(autouse=True)
def reset_registry():
    clear()
    yield
    clear()


def test_register_and_get_whatsapp():
    adapter = WhatsAppCloudAdapter()
    register(adapter)
    result = get("whatsapp_cloud")
    assert result is adapter


def test_register_and_get_telegram():
    adapter = TelegramAdapter()
    register(adapter)
    result = get("telegram")
    assert result is adapter


def test_get_unknown_raises_key_error():
    with pytest.raises(KeyError, match="canal_inexistente"):
        get("canal_inexistente")


def test_registered_channels_list():
    register(WhatsAppCloudAdapter())
    channels = registered_channels()
    assert "whatsapp_cloud" in channels


def test_clear_empties_registry():
    register(WhatsAppCloudAdapter())
    clear()
    with pytest.raises(KeyError):
        get("whatsapp_cloud")
