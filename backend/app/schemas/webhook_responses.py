from ._strict_base import StrictModel

"""Pydantic models for webhook endpoint responses."""


class WebhookAckResponse(StrictModel):
    """Standard acknowledgement payload returned by webhook endpoints."""

    ok: bool = True


__all__ = ["WebhookAckResponse"]
