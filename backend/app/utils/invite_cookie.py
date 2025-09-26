"""Utilities for invite verification cookies."""

from ..core.config import settings


def invite_cookie_name() -> str:
    """Return the invite verification cookie name for the current site mode."""
    return f"iv_{settings.site_mode}"
