# backend/app/schemas/review.py
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic.functional_validators import field_validator


class ReviewSubmitRequest(BaseModel):
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


class ReviewItem(BaseModel):
    id: str
    rating: int
    review_text: Optional[str]
    created_at: datetime
    instructor_service_id: str
    reviewer_display_name: Optional[str] = None


class ReviewSubmitResponse(ReviewItem):
    tip_status: Optional[str] = None
    tip_client_secret: Optional[str] = None


class ReviewResponseModel(BaseModel):
    id: str
    review_id: str
    instructor_id: str
    response_text: str
    created_at: datetime


class InstructorRatingsResponse(BaseModel):
    overall: Dict[str, Any]
    by_service: List[Dict[str, Any]] = Field(default_factory=list)
    confidence_level: str = Field(..., pattern="^(new|establishing|established|trusted)$")


class ReviewListResponse(BaseModel):
    reviews: List[ReviewItem]


class SearchRatingResponse(BaseModel):
    primary_rating: Optional[float]
    review_count: int
    is_service_specific: bool


class RatingsBatchRequest(BaseModel):
    instructor_ids: List[str] = Field(..., min_length=1)


class RatingsBatchItem(BaseModel):
    instructor_id: str
    rating: Optional[float]
    review_count: int


class RatingsBatchResponse(BaseModel):
    results: List[RatingsBatchItem]


class ReviewListPageResponse(BaseModel):
    reviews: List[ReviewItem]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool
