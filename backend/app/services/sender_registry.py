"""Sender profile registry sourced from configuration settings."""

from __future__ import annotations

from ..core.config import SenderProfileResolved, settings


def get_sender(key: str | None) -> SenderProfileResolved:
    """Return the resolved sender profile for the provided key."""

    return settings.resolve_sender_profile(key)
