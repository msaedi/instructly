"""Strict schema baselines with forbidden extras by default."""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Neutral strict base for response DTOs."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class StrictRequestModel(StrictModel):
    """Request DTO base that always forbids unexpected fields."""

    # Requests inherit strict config and may later grow request-specific tweaks.
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
