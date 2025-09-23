"""Strict request model enforcing forbidden extras by default."""

from pydantic import BaseModel, ConfigDict


class StrictRequestModel(BaseModel):
    """Request DTO base that always forbids unexpected fields."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )
