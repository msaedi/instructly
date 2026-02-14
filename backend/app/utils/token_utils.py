"""JWT token utility helpers."""

from __future__ import annotations

from typing import Any, Mapping


def parse_token_iat(payload: Mapping[str, Any]) -> int | None:
    """Parse the JWT iat claim as integer epoch seconds."""
    iat_obj = payload.get("iat")
    if isinstance(iat_obj, int):
        return iat_obj
    if isinstance(iat_obj, float):
        return int(iat_obj)
    if isinstance(iat_obj, str):
        try:
            return int(iat_obj)
        except ValueError:
            return None
    return None
