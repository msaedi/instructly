# backend/app/routes/v1/reviews.py
"""
Reviews routes - API v1

Versioned review endpoints under /api/v1/reviews.
All business logic delegated to ReviewService.

Endpoints:
    POST /                                → Submit a new review (student)
    GET /instructor/{instructor_id}/ratings → Get instructor ratings (public)
    GET /instructor/{instructor_id}/recent  → Recent reviews with pagination (public)
    GET /instructor/{instructor_id}/search-rating → Rating for search context (public)
    GET /booking/{booking_id}             → Get review for specific booking (student)
    POST /booking/existing                → Check existing reviews for bookings (student)
    POST /{review_id}/respond             → Instructor responds to review
    POST /ratings/batch                   → Batch ratings lookup (public)
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, NoReturn, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user, get_current_student
from ...core.exceptions import DomainException
from ...database import get_db
from ...models.user import User
from ...ratelimit.dependency import rate_limit as new_rate_limit
from ...repositories.booking_repository import BookingRepository
from ...repositories.instructor_profile_repository import InstructorProfileRepository
from ...repositories.review_repository import ReviewTipRepository
from ...schemas.review import (
    ExistingReviewIdsResponse,
    InstructorRatingsResponse,
    RatingsBatchRequest,
    RatingsBatchResponse,
    ReviewItem,
    ReviewListPageResponse,
    ReviewResponseModel,
    ReviewSubmitRequest,
    ReviewSubmitResponse,
    SearchRatingResponse,
)
from ...services.config_service import ConfigService
from ...services.pricing_service import PricingService
from ...services.review_service import ReviewService
from ...services.stripe_service import StripeService

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["reviews-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


def get_review_service(db: Session = Depends(get_db)) -> ReviewService:
    return ReviewService(db)


def _display_name(user: Optional[User]) -> Optional[str]:
    """Format user display name as 'FirstName L.'"""
    if not user:
        return None
    first = (user.first_name or "").strip()
    last_init = (user.last_name or " ")[:1]
    return f"{first} {last_init}.".strip() if first else None


def handle_domain_exception(exc: DomainException) -> NoReturn:
    """Convert domain exceptions to HTTP exceptions."""
    if hasattr(exc, "to_http_exception"):
        raise exc.to_http_exception()
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# =============================================================================
# Static routes first (before dynamic routes with path parameters)
# =============================================================================


@router.post(
    "/ratings/batch",
    response_model=RatingsBatchResponse,
    dependencies=[Depends(new_rate_limit("read"))],
)
def get_ratings_batch(
    payload: RatingsBatchRequest = Body(...),
    service: ReviewService = Depends(get_review_service),
) -> RatingsBatchResponse:
    """
    Get ratings for multiple instructors in a single request.

    Public endpoint - no authentication required.
    """
    instructor_ids = payload.instructor_ids
    results: List[Dict[str, Any]] = []
    for iid in instructor_ids:
        data = service.get_instructor_ratings(iid)
        total = int(data.get("overall", {}).get("total_reviews", 0))
        rating = (
            float(data.get("overall", {}).get("rating", 0.0))
            if total >= service.config.min_reviews_to_display
            else None
        )
        results.append({"instructor_id": iid, "rating": rating, "review_count": total})
    return RatingsBatchResponse(results=results)


@router.post(
    "/booking/existing",
    response_model=ExistingReviewIdsResponse,
    dependencies=[Depends(new_rate_limit("read"))],
)
def get_existing_reviews_for_bookings(
    booking_ids: List[str] = Body(...),
    current_user: User = Depends(get_current_student),
    service: ReviewService = Depends(get_review_service),
) -> ExistingReviewIdsResponse:
    """
    Check which bookings already have reviews.

    Returns list of booking IDs that have existing reviews.
    Only returns reviews for bookings owned by the current student.
    """
    try:
        setattr(service.db, "current_student_id", current_user.id)
    except Exception:
        pass

    owner_repo = BookingRepository(service.db)
    owned_ids = owner_repo.filter_owned_booking_ids(booking_ids, current_user.id)
    if not owned_ids:
        return ExistingReviewIdsResponse([])
    review_ids = service.get_existing_reviews_for_bookings(owned_ids)
    return ExistingReviewIdsResponse([str(rid) for rid in review_ids])


@router.post(
    "",
    response_model=ReviewSubmitResponse,
    dependencies=[Depends(new_rate_limit("write"))],
)
async def submit_review(
    payload: ReviewSubmitRequest = Body(...),
    current_user: User = Depends(get_current_student),
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
) -> ReviewSubmitResponse:
    """
    Submit a review for a completed booking.

    Students can submit one review per booking.
    Optionally include a tip amount for the instructor.
    """
    try:
        review = service.submit_review(
            student_id=current_user.id,
            booking_id=payload.booking_id,
            rating=payload.rating,
            review_text=payload.review_text,
            tip_amount_cents=payload.tip_amount_cents,
        )

        tip_client_secret: Optional[str] = None
        tip_status: Optional[str] = None

        tip_repo = ReviewTipRepository(db)
        tip_record = None
        try:
            tip_record = tip_repo.get_by_review_id(review.id)
        except Exception:
            tip_record = None

        # If tip provided, create a standalone PaymentIntent for the tip
        if payload.tip_amount_cents and payload.tip_amount_cents > 0:
            try:
                config_service = ConfigService(db)
                pricing_service = PricingService(db)
                stripe_service = StripeService(
                    db,
                    config_service=config_service,
                    pricing_service=pricing_service,
                )
                customer = stripe_service.get_or_create_customer(current_user.id)
                instr_repo = InstructorProfileRepository(db)
                instructor_profile = instr_repo.get_by_user_id(review.instructor_id)
                if not instructor_profile:
                    raise HTTPException(
                        status_code=400, detail="Instructor profile not found for tip"
                    )
                connected = (
                    stripe_service.payment_repository.get_connected_account_by_instructor_id(
                        instructor_profile.id
                    )
                )
                if not connected or not connected.stripe_account_id:
                    raise HTTPException(
                        status_code=400, detail="Instructor is not set up to receive tips"
                    )

                # Create PaymentIntent for the tip as a destination charge
                pi_record = stripe_service.create_payment_intent(
                    booking_id=review.booking_id,
                    customer_id=customer.stripe_customer_id,
                    destination_account_id=connected.stripe_account_id,
                    amount_cents=int(payload.tip_amount_cents),
                    charge_context=None,
                )

                if tip_record:
                    tip_repo.set_payment_intent_details(
                        tip_record.id,
                        stripe_payment_intent_id=pi_record.stripe_payment_intent_id,
                        status=pi_record.status,
                    )

                # Try auto-confirm with student's default payment method
                default_pm = stripe_service.payment_repository.get_default_payment_method(
                    current_user.id
                )
                if default_pm and default_pm.stripe_payment_method_id:
                    try:
                        pi_after_confirm = stripe_service.confirm_payment_intent(
                            pi_record.stripe_payment_intent_id, default_pm.stripe_payment_method_id
                        )
                        tip_status = pi_after_confirm.status
                        if tip_record:
                            tip_repo.set_payment_intent_details(
                                tip_record.id,
                                stripe_payment_intent_id=pi_after_confirm.id,
                                status=pi_after_confirm.status,
                                processed_at=datetime.now(timezone.utc)
                                if pi_after_confirm.status == "succeeded"
                                else None,
                            )
                        # If further action required (SCA), provide client_secret
                        if tip_status in ("requires_action", "requires_confirmation"):
                            try:
                                import stripe as _stripe

                                if getattr(stripe_service, "stripe_configured", False):
                                    pi = _stripe.PaymentIntent.retrieve(
                                        pi_record.stripe_payment_intent_id
                                    )
                                    tip_client_secret = getattr(pi, "client_secret", None)
                            except Exception:
                                tip_client_secret = None
                    except Exception:
                        tip_status = "requires_payment_method"
                        tip_client_secret = None
                        if tip_record:
                            tip_repo.set_payment_intent_details(
                                tip_record.id,
                                stripe_payment_intent_id=pi_record.stripe_payment_intent_id,
                                status=tip_status,
                            )
                else:
                    tip_status = "requires_payment_method"
                    tip_client_secret = None
                    if tip_record:
                        tip_repo.set_payment_intent_details(
                            tip_record.id,
                            stripe_payment_intent_id=pi_record.stripe_payment_intent_id,
                            status=tip_status,
                        )
            except HTTPException:
                raise
            except Exception:
                tip_status = "failed"
                tip_client_secret = None
                if tip_record:
                    tip_repo.set_payment_intent_details(
                        tip_record.id,
                        stripe_payment_intent_id=tip_record.stripe_payment_intent_id,
                        status=tip_status,
                    )

        return ReviewSubmitResponse(
            id=review.id,
            rating=review.rating,
            review_text=review.review_text,
            created_at=review.created_at,
            instructor_service_id=review.instructor_service_id,
            reviewer_display_name=_display_name(current_user),
            tip_status=tip_status,
            tip_client_secret=tip_client_secret,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =============================================================================
# Dynamic routes with path parameters
# =============================================================================


@router.get(
    "/instructor/{instructor_id}/ratings",
    response_model=InstructorRatingsResponse,
    dependencies=[Depends(new_rate_limit("read"))],
)
def get_instructor_ratings(
    instructor_id: str = Path(
        ...,
        description="Instructor ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    service: ReviewService = Depends(get_review_service),
) -> InstructorRatingsResponse:
    """
    Get rating statistics for an instructor.

    Public endpoint - no authentication required.
    Returns overall rating, per-service ratings, and rating distribution.
    """
    return InstructorRatingsResponse(**service.get_instructor_ratings(instructor_id))


@router.get(
    "/instructor/{instructor_id}/search-rating",
    response_model=SearchRatingResponse,
    dependencies=[Depends(new_rate_limit("read"))],
)
def get_search_rating(
    instructor_id: str = Path(
        ...,
        description="Instructor ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    instructor_service_id: Optional[str] = Query(None),
    service: ReviewService = Depends(get_review_service),
) -> SearchRatingResponse:
    """
    Get compact rating info for search results context.

    Public endpoint - no authentication required.
    Returns rating and review count optimized for search result display.
    """
    return SearchRatingResponse(
        **service.get_rating_for_search_context(instructor_id, instructor_service_id)
    )


@router.get(
    "/instructor/{instructor_id}/recent",
    response_model=ReviewListPageResponse,
    dependencies=[Depends(new_rate_limit("read"))],
)
def get_recent_reviews(
    instructor_id: str = Path(
        ...,
        description="Instructor ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    instructor_service_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    rating: Optional[int] = Query(None, ge=1, le=5),
    with_text: Optional[bool] = Query(None),
    service: ReviewService = Depends(get_review_service),
) -> ReviewListPageResponse:
    """
    Get paginated list of recent reviews for an instructor.

    Public endpoint - no authentication required.
    Supports filtering by rating, service, and text presence.
    """
    if rating is not None:
        min_rating = None
    reviews: List[Any] = service.get_recent_reviews(
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        limit=limit,
        page=page,
        min_rating=min_rating,
        rating=rating,
        with_text=with_text,
    )
    total = service.count_recent_reviews(
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        min_rating=min_rating,
        rating=rating,
        with_text=with_text,
    )
    items: List[ReviewItem] = []
    for r in reviews:
        reviewer_name = None
        try:
            from ...models.user import User as _User

            user = service.db.query(_User).filter(_User.id == r.student_id).first()
            reviewer_name = _display_name(user)
        except Exception:
            reviewer_name = None
        items.append(
            ReviewItem(
                id=r.id,
                rating=r.rating,
                review_text=r.review_text,
                created_at=r.created_at,
                instructor_service_id=r.instructor_service_id,
                reviewer_display_name=reviewer_name,
            )
        )
    has_next = page * limit < total
    has_prev = page > 1
    return ReviewListPageResponse(
        reviews=items,
        total=total,
        page=page,
        per_page=limit,
        has_next=has_next,
        has_prev=has_prev,
    )


@router.get(
    "/booking/{booking_id}",
    response_model=Optional[ReviewItem],
    dependencies=[Depends(new_rate_limit("read"))],
)
def get_review_for_booking(
    booking_id: str = Path(
        ...,
        description="Booking ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    current_user: User = Depends(get_current_student),
    service: ReviewService = Depends(get_review_service),
) -> Optional[ReviewItem]:
    """
    Get the review for a specific booking.

    Students can only view reviews they submitted.
    Returns None if no review exists for the booking.
    """
    review = service.get_review_for_booking(booking_id)
    if not review:
        return None
    if review.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return ReviewItem(
        id=review.id,
        rating=review.rating,
        review_text=review.review_text,
        created_at=review.created_at,
        instructor_service_id=review.instructor_service_id,
        reviewer_display_name=_display_name(current_user),
    )


@router.post(
    "/{review_id}/respond",
    response_model=ReviewResponseModel,
    dependencies=[Depends(new_rate_limit("write"))],
)
def respond_to_review(
    review_id: str = Path(
        ...,
        description="Review ULID",
        pattern=ULID_PATH_PATTERN,
        examples=["01HF4G12ABCDEF3456789XYZAB"],
    ),
    response_text: str = Body(..., embed=True),
    current_user: User = Depends(get_current_active_user),
    service: ReviewService = Depends(get_review_service),
) -> ReviewResponseModel:
    """
    Add an instructor response to a review.

    Only the instructor who received the review can respond.
    """
    try:
        response = service.add_instructor_response(
            review_id=review_id, instructor_id=current_user.id, response_text=response_text
        )
        return ReviewResponseModel(
            id=response.id,
            review_id=response.review_id,
            instructor_id=response.instructor_id,
            response_text=response.response_text,
            created_at=response.created_at,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
