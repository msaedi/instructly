"""JWT token utility helpers."""

from __future__ import annotations

from typing import Any, Mapping


def parse_epoch_claim(payload: Mapping[str, Any], claim: str = "iat") -> int | None:
    """Parse a JWT epoch claim (iat, exp, nbf, …) as integer seconds."""
    value = payload.get(claim)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def parse_token_iat(payload: Mapping[str, Any]) -> int | None:
    """Parse the JWT iat claim as integer epoch seconds."""
    return parse_epoch_claim(payload, "iat")
