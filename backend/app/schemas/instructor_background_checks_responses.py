"""Strict response schemas for instructor background check routes."""

from pydantic import Field

from ._strict_base import StrictModel
from .bgc import BackgroundCheckStatusLiteral


class ConsentResponse(StrictModel):
    """Acknowledgement returned after recording consent."""

    ok: bool = Field(default=True, description="Whether the consent record was stored")


class MockStatusResponse(StrictModel):
    """Response returned by non-production mock status changers."""

    ok: bool = Field(default=True, description="Whether the mock update succeeded")
    status: BackgroundCheckStatusLiteral = Field(
        ..., description="Background check status after the mock update"
    )


__all__ = [
    "ConsentResponse",
    "MockStatusResponse",
]
