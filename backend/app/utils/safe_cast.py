"""Shared safe-casting helpers for booking payload shaping."""

from __future__ import annotations

from decimal import Decimal


def safe_float(value: object) -> float | None:
    """Safely coerce common numeric inputs to float."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def safe_str(value: object) -> str | None:
    """Return string values while ignoring non-string inputs."""
    return value if isinstance(value, str) else None
