"""Strict request model that only forbids extras when STRICT_SCHEMAS=1."""

import os

from pydantic import BaseModel, ConfigDict

STRICT = os.getenv("STRICT_SCHEMAS", "0").lower() in {"1", "true", "yes"}


class StrictRequestModel(BaseModel):
    """Request DTO base that toggles extra handling via STRICT_SCHEMAS."""

    model_config = ConfigDict(
        extra="forbid" if STRICT else "ignore",
        validate_assignment=True,
    )
