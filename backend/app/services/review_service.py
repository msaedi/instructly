# backend/app/services/review_service.py
"""
ReviewService: business logic for reviews/ratings.

Implements:
- Eligibility and submission (one per booking, within window)
- Optional tip creation (async processing elsewhere)
- Aggregation with Bayesian averaging
- Cache-first reads with targeted invalidation
- Instructor response (one per review) with ownership enforcement
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TypedDict, cast

from sqlalchemy.orm import Session

from ..core.exceptions import NotFoundException, ValidationException
from ..models.booking import BookingStatus
from ..models.review import Review, ReviewResponse, ReviewStatus
from ..repositories.booking_repository import BookingRepository
from ..repositories.factory import RepositoryFactory
from ..repositories.review_repository import (
    ReviewRepository,
    ReviewResponseRepository,
    ReviewTipRepository,
)
from .base import BaseService
from .cache_service import CacheService
from .ratings_config import DEFAULT_RATINGS_CONFIG, RatingsConfig
from .ratings_math import (
    compute_dirichlet_rating,
    compute_simple_shrinkage,
    confidence_label,
    dirichlet_prior_mean,
    display_policy,
)


class RatingComputation(TypedDict):
    rating: float
    total_reviews: int
    display_rating: str | None


class ServiceBreakdownSummary(TypedDict):
    instructor_service_id: str
    rating: float | None
    review_count: int
    display_rating: str | None


class InstructorRatingsSummary(TypedDict):
    overall: RatingComputation
    by_service: list[ServiceBreakdownSummary]
    confidence_level: str


class SearchRatingSummary(TypedDict):
    primary_rating: float | None
    review_count: int
    is_service_specific: bool


class ReviewService(BaseService):
    """Service layer for reviews & ratings."""

    # Policy and math configuration
    REVIEW_WINDOW_DAYS = 30
    CACHE_VERSION = "v2"

    def __init__(
        self,
        db: Session,
        cache: Optional[CacheService] = None,
        config: RatingsConfig = DEFAULT_RATINGS_CONFIG,
    ) -> None:
        super().__init__(db, cache)
        self.repository: ReviewRepository = ReviewRepository(db)
        self.response_repository: ReviewResponseRepository = ReviewResponseRepository(db)
        self.tip_repository: ReviewTipRepository = ReviewTipRepository(db)
        self.booking_repository: BookingRepository = RepositoryFactory.create_booking_repository(db)
        self.config = config

    @BaseService.measure_operation("submit_review")
    def submit_review(
        self,
        *,
        student_id: str,
        booking_id: str,
        rating: int,
        review_text: Optional[str] = None,
        tip_amount_cents: Optional[int] = None,
    ) -> Review:
        """Submit a review for a completed booking."""
        if rating is None or rating < 1 or rating > 5:
            raise ValidationException("Rating must be an integer between 1 and 5")
        if review_text is not None:
            text = review_text.strip()
            if len(text) > 500:
                raise ValidationException("Review text cannot exceed 500 characters")
            review_text = text

        booking = self.booking_repository.get_by_id(booking_id)
        if not booking:
            raise NotFoundException("Booking not found")

        # Eligibility
        if booking.student_id != student_id:
            raise ValidationException("You can only review your own booking")
        if booking.status not in [BookingStatus.COMPLETED, BookingStatus.CONFIRMED]:
            raise ValidationException("Only completed bookings can be reviewed")

        # Determine effective completion time to anchor review window
        effective_completed_at_utc: Optional[datetime] = booking.completed_at

        # If completion timestamp is missing, derive it from scheduled end for CONFIRMED/COMPLETED
        if effective_completed_at_utc is None and booking.status in [
            BookingStatus.CONFIRMED,
            BookingStatus.COMPLETED,
        ]:
            from ..core.timezone_utils import get_user_now_by_id

            # Get user's current time with safe fallback to UTC
            try:
                user_now = get_user_now_by_id(student_id, self.db)
            except Exception:
                user_now = datetime.now(timezone.utc)

            user_tz = user_now.tzinfo
            today = user_now.date()
            now_time = user_now.time()

            # For CONFIRMED (not explicitly completed), block submission until after scheduled end time
            if booking.status == BookingStatus.CONFIRMED:
                if booking.booking_date > today:
                    raise ValidationException("You can submit a review after the lesson ends")
                if (
                    booking.booking_date == today
                    and booking.end_time
                    and now_time < booking.end_time
                ):
                    raise ValidationException("You can submit a review after the lesson ends")

            # Compute the scheduled end datetime in user's timezone, then convert to UTC
            if booking.end_time is not None:
                local_end_naive = datetime.combine(booking.booking_date, booking.end_time)
                if user_tz and hasattr(user_tz, "localize"):
                    tz_with_localize = cast(Any, user_tz)  # pytz tzinfo exposes localize()
                    local_end = tz_with_localize.localize(local_end_naive)
                else:
                    local_end = local_end_naive.replace(tzinfo=user_tz or timezone.utc)
                effective_completed_at_utc = local_end.astimezone(timezone.utc)
            else:
                # Fallback to user's now if end_time missing
                effective_completed_at_utc = user_now.astimezone(timezone.utc)

        # Guard against None and enforce 30-day window from effective completion
        if effective_completed_at_utc is None:
            raise ValidationException("Booking completion time not recorded")
        now = datetime.now(timezone.utc)
        if now > effective_completed_at_utc + timedelta(days=self.REVIEW_WINDOW_DAYS):
            raise ValidationException("Review window has expired")

        if self.repository.exists_for_booking(booking_id):
            raise ValidationException("Review already submitted for this booking")

        status = self._moderate_text(review_text)

        with self.transaction():
            review = self.repository.create_review(
                booking_id=booking_id,
                student_id=student_id,
                instructor_id=booking.instructor_id,
                instructor_service_id=booking.instructor_service_id,
                rating=rating,
                review_text=review_text,
                status=status,
                is_verified=True,
                booking_completed_at=effective_completed_at_utc,
            )

            if tip_amount_cents and tip_amount_cents > 0:
                try:
                    self.tip_repository.create_tip(
                        review_id=review.id,
                        amount_cents=int(tip_amount_cents),
                        status="pending",
                    )
                except Exception:
                    # Non-blocking; log and continue
                    self.logger.warning("Failed to create review tip record; continuing")

        # Invalidate caches
        self._invalidate_instructor_caches(booking.instructor_id)

        return review

    @BaseService.measure_operation("get_instructor_ratings")
    def get_instructor_ratings(self, instructor_id: str) -> InstructorRatingsSummary:
        cache_key = f"ratings:{self.CACHE_VERSION}:instructor:{instructor_id}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cast(InstructorRatingsSummary, cached)

        # Compute Dirichlet-smoothed rating with recency weighting
        overall = self._compute_dirichlet_rating(instructor_id)
        breakdown_rows = self.repository.get_service_breakdown(instructor_id)

        by_service: list[ServiceBreakdownSummary] = []
        for s in breakdown_rows:
            # For service breakdown, fall back to simple shrinkage per-service to avoid heavy histogram compute
            rating_sum_raw = s.get("rating_sum", 0) or 0
            review_count_raw = s.get("review_count", 0) or 0
            bayes = compute_simple_shrinkage(
                float(rating_sum_raw), int(review_count_raw), self.config
            )
            count = int(review_count_raw)
            by_service.append(
                {
                    "instructor_service_id": str(s["instructor_service_id"]),
                    "rating": round(bayes, 1)
                    if count >= self.config.min_reviews_to_display
                    else None,
                    "review_count": count,
                    "display_rating": display_policy(bayes, count, self.config),
                }
            )

        result: InstructorRatingsSummary = {
            "overall": overall,
            "by_service": by_service,
            "confidence_level": confidence_label(overall["total_reviews"]),
        }

        if self.cache:
            self.cache.set(cache_key, result, ttl=300)

        return result

    @BaseService.measure_operation("get_recent_reviews")
    def get_recent_reviews(
        self,
        *,
        instructor_id: str,
        instructor_service_id: Optional[str] = None,
        limit: int = 10,
        page: int = 1,
        min_rating: Optional[int] = None,
        with_text: Optional[bool] = None,
    ) -> list[Review]:
        offset = max(0, (page - 1) * max(1, limit))
        return self.repository.get_recent_reviews(
            instructor_id,
            instructor_service_id,
            limit,
            offset,
            min_rating=min_rating,
            with_text=with_text,
        )

    @BaseService.measure_operation("count_recent_reviews")
    def count_recent_reviews(
        self,
        *,
        instructor_id: str,
        instructor_service_id: Optional[str] = None,
        min_rating: Optional[int] = None,
        with_text: Optional[bool] = None,
    ) -> int:
        count = self.repository.count_recent_reviews(
            instructor_id,
            instructor_service_id,
            min_rating=min_rating,
            with_text=with_text,
        )
        return int(count)

    @BaseService.measure_operation("get_review_for_booking")
    def get_review_for_booking(self, booking_id: str) -> Optional[Review]:
        return self.repository.get_by_booking_id(booking_id)

    @BaseService.measure_operation("get_existing_reviews_for_bookings")
    def get_existing_reviews_for_bookings(self, booking_ids: list[str]) -> list[str]:
        if not booking_ids:
            return []
        try:
            # Restrict to current user's bookings: derive student_id from auth context if available.
            # The service layer does not have direct auth context; routes enforce it. As an extra guard,
            # filter the provided booking_ids through ownership based on the booking repository and current
            # transaction session when a student context is attached to the DB session info.
            current_student_id = getattr(self.db, "current_student_id", None)
            if current_student_id:
                owned = self.booking_repository.filter_owned_booking_ids(
                    booking_ids, current_student_id
                )
                if not owned:
                    return []
                return self.repository.get_existing_for_bookings(owned)
            # Fallback: route should have already enforced ownership; return checked ids
            return self.repository.get_existing_for_bookings(booking_ids)
        except Exception:
            return []

    @BaseService.measure_operation("get_rating_for_search_context")
    def get_rating_for_search_context(
        self, instructor_id: str, instructor_service_id: Optional[str] = None
    ) -> SearchRatingSummary:
        cache_key = (
            f"ratings:search:{self.CACHE_VERSION}:{instructor_id}:{instructor_service_id or 'all'}"
        )
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cast(SearchRatingSummary, cached)

        if instructor_service_id:
            sr = self._compute_dirichlet_rating_for_service(instructor_id, instructor_service_id)
            result: SearchRatingSummary = {
                "primary_rating": sr["rating"]
                if sr["total_reviews"] >= self.config.min_reviews_to_display
                else None,
                "review_count": sr["total_reviews"],
                "is_service_specific": True,
            }
            if self.cache:
                self.cache.set(cache_key, result, ttl=300)
            return result

        overall = self._compute_dirichlet_rating(instructor_id)
        overall_result: SearchRatingSummary = {
            "primary_rating": overall["rating"]
            if overall["total_reviews"] >= self.config.min_reviews_to_display
            else None,
            "review_count": overall["total_reviews"],
            "is_service_specific": False,
        }
        if self.cache:
            self.cache.set(cache_key, overall_result, ttl=300)
        return overall_result

    @BaseService.measure_operation("add_instructor_response")
    def add_instructor_response(
        self, *, review_id: str, instructor_id: str, response_text: str
    ) -> ReviewResponse:
        if not response_text or not response_text.strip():
            raise ValidationException("Response text cannot be empty")
        if len(response_text.strip()) > 500:
            raise ValidationException("Response text cannot exceed 500 characters")

        review = self.repository.get_by_id(review_id)
        if not review:
            raise NotFoundException("Review not found")
        if review.instructor_id != instructor_id:
            raise ValidationException("You can only respond to reviews on your own bookings")
        if self.response_repository.exists_for_review(review_id):
            raise ValidationException("Response already submitted for this review")

        with self.transaction():
            response = self.response_repository.create_response(
                review_id=review_id,
                instructor_id=instructor_id,
                response_text=response_text.strip(),
            )

        # Invalidate caches
        self._invalidate_instructor_caches(instructor_id)

        return response

    # --------- Helpers ---------
    def _moderate_text(self, text: Optional[str]) -> ReviewStatus:
        if not text:
            return ReviewStatus.PUBLISHED
        t = text.strip()
        if len(t) < 3:
            return ReviewStatus.FLAGGED
        if any(ch * 10 in t for ch in set(t)):
            return ReviewStatus.FLAGGED
        return ReviewStatus.PUBLISHED

    def _bayesian(self, rating_sum: int, count: int) -> float:
        # Backward-compatible wrapper for simple shrinkage used in per-service breakdown.
        return float(compute_simple_shrinkage(rating_sum, count))

    def _compute_dirichlet_rating(self, instructor_id: str) -> RatingComputation:
        """Compute overall rating using a Dirichlet prior with recency weighting.

        Returns a dict: { rating: float, total_reviews: int, display_rating: str|None }
        """
        reviews = self.repository.get_published_verified_for_instructor(instructor_id)
        result = compute_dirichlet_rating(reviews, config=self.config)
        rating_value = float(result.get("rating", 0.0) or 0.0)
        total_reviews = int(result.get("total_reviews", 0) or 0)
        return {
            "rating": rating_value,
            "total_reviews": total_reviews,
            "display_rating": self._display(rating_value, total_reviews),
        }

    def _dirichlet_prior_mean(self) -> float:
        return float(dirichlet_prior_mean(self.config))

    def _compute_dirichlet_rating_for_service(
        self, instructor_id: str, instructor_service_id: str
    ) -> RatingComputation:
        """Compute service-specific rating using a Dirichlet prior with recency weighting."""
        reviews = self.repository.get_published_verified_for_instructor(
            instructor_id, instructor_service_id
        )
        result = compute_dirichlet_rating(reviews, config=self.config)
        rating_value = float(result.get("rating", 0.0) or 0.0)
        total_reviews = int(result.get("total_reviews", 0) or 0)
        return {
            "rating": rating_value,
            "total_reviews": total_reviews,
            "display_rating": self._display(rating_value, total_reviews),
        }

    def _display(self, rating: float, count: int) -> Optional[str]:
        if count < self.config.min_reviews_to_display:
            return None
        if count < 5:
            return f"{round(rating, 1)}★ (New)"
        return f"{round(rating, 1)}★"

    def _confidence(self, count: int) -> str:
        if count < 5:
            return "new"
        if count < 25:
            return "establishing"
        if count < 100:
            return "established"
        return "trusted"

    def _invalidate_instructor_caches(self, instructor_id: str) -> None:
        if not self.cache:
            return
        try:
            # Specific keys only; caller may manage a set to expand if needed
            # Legacy keys
            self.cache.delete(f"ratings:instructor:{instructor_id}")
            self.cache.delete(f"ratings:search:{instructor_id}:all")
            # Versioned keys
            self.cache.delete(f"ratings:{self.CACHE_VERSION}:instructor:{instructor_id}")
            self.cache.delete(f"ratings:search:{self.CACHE_VERSION}:{instructor_id}:all")
        except Exception:
            pass
