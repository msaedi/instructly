"""Strict response schemas for gated diagnostic endpoints."""

from ._strict_base import StrictModel


class GatedPingResponse(StrictModel):
    """Simple response indicating gated ping success."""

    ok: bool


__all__ = ["GatedPingResponse"]
