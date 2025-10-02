"""Pydantic models for webhook endpoint responses."""

from pydantic import BaseModel, ConfigDict


class WebhookAckResponse(BaseModel):
    """Standard acknowledgement payload returned by webhook endpoints."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    ok: bool = True


__all__ = ["WebhookAckResponse"]
