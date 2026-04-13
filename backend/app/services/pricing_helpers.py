"""Private helpers shared across pricing-related service modules."""

from __future__ import annotations

from typing import Any


def _coerce_tier_bound(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
