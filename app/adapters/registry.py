"""Registry simples de adapters por channel_id."""
from __future__ import annotations

from app.adapters.base import ChannelAdapter


_registry: dict[str, ChannelAdapter] = {}


def register(adapter: ChannelAdapter) -> None:
    _registry[adapter.channel_id] = adapter


def get(channel_id: str) -> ChannelAdapter:
    if channel_id not in _registry:
        raise KeyError(f"No adapter registered for channel: {channel_id}")
    return _registry[channel_id]


def all_registered() -> list[str]:
    return list(_registry.keys())
