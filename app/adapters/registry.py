"""Registry de adapters por channel_id.

Integrado ao lifespan da aplicação (`app.main`). Cada adapter ativo é
registrado uma única vez no startup; o pipeline e os routes consultam
via `get(channel_id)` para selecionar o adapter correto.
"""
from __future__ import annotations

from app.adapters.base import ChannelAdapter


_registry: dict[str, ChannelAdapter] = {}


def register(adapter: ChannelAdapter) -> None:
    """Register a channel adapter. Called once during lifespan startup."""
    _registry[adapter.channel_id] = adapter


def get(channel_id: str) -> ChannelAdapter:
    """Get adapter by channel_id. Raises KeyError if not registered."""
    if channel_id not in _registry:
        raise KeyError(
            f"No adapter registered for channel '{channel_id}'. "
            f"Registered: {list(_registry.keys())}"
        )
    return _registry[channel_id]


def registered_channels() -> list[str]:
    """List all registered channel IDs."""
    return list(_registry.keys())


def clear() -> None:
    """Clear registry. Used in tests only."""
    _registry.clear()
