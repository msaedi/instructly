# backend/app/schemas/review.py
from datetime import datetime
from typing import List, Optional

from pydantic import ConfigDict, Field, RootModel
from pydantic.functional_validators import field_validator

from ._strict_base import StrictModel, StrictRequestModel


class OverallRatingStats(StrictModel):
    """Overall rating statistics computed using Dirichlet smoothing."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    rating: float = Field(description="Computed rating (Dirichlet-smoothed)")
    total_reviews: int = Field(description="Total number of reviews")
    display_rating: Optional[str] = Field(
        default=None,
        description="Display-formatted rating (e.g., '4.5★') or None if below threshold",
    )


class ServiceRatingStats(StrictModel):
    """Per-service rating statistics."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    instructor_service_id: str = Field(description="ID of the instructor's service offering")
    rating: Optional[float] = Field(
        default=None, description="Computed rating or None if below min_reviews threshold"
    )
    review_count: int = Field(description="Number of reviews for this service")
    display_rating: Optional[str] = Field(
        default=None, description="Display-formatted rating or None if below threshold"
    )


class ReviewSubmitRequest(StrictRequestModel):
    booking_id: str
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = Field(None, max_length=500)
    tip_amount_cents: Optional[int] = Field(None, gt=0)

    @field_validator("review_text")
    @classmethod
    def _clean_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        if v2 and len(v2) < 3:
            raise ValueError("Review text too short")
        return v2


class ReviewItem(StrictModel):
    id: str
    rating: int
    review_text: Optional[str]
    created_at: datetime
    instructor_service_id: str
    reviewer_display_name: Optional[str] = None


class ReviewSubmitResponse(ReviewItem):
    tip_status: Optional[str] = None
    tip_client_secret: Optional[str] = None


class ReviewResponseModel(StrictModel):
    id: str
    review_id: str
    instructor_id: str
    response_text: str
    created_at: datetime


class InstructorRatingsResponse(StrictModel):
    """Instructor rating statistics with overall and per-service breakdown."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    overall: OverallRatingStats = Field(description="Overall rating statistics")
    by_service: List[ServiceRatingStats] = Field(
        default_factory=list, description="Per-service rating breakdown"
    )
    confidence_level: str = Field(..., pattern="^(new|establishing|established|trusted)$")


class ReviewListResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    reviews: List[ReviewItem]


class SearchRatingResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    primary_rating: Optional[float]
    review_count: int
    is_service_specific: bool


class RatingsBatchRequest(StrictRequestModel):
    instructor_ids: List[str] = Field(..., min_length=1)


class RatingsBatchItem(StrictModel):
    instructor_id: str
    rating: Optional[float]
    review_count: int


class RatingsBatchResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    results: List[RatingsBatchItem]


class ReviewListPageResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    reviews: List[ReviewItem]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class ExistingReviewIdsResponse(RootModel[List[str]]):
    pass
