# backend/app/routes/reviews.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user, get_current_student
from ..database import get_db
from ..models.user import User
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..schemas.review import (
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
from ..services.review_service import ReviewService
from ..services.stripe_service import StripeService

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def get_review_service(db: Session = Depends(get_db)) -> ReviewService:
    return ReviewService(db)


def _display_name(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    first = (user.first_name or "").strip()
    last_init = (user.last_name or " ")[:1]
    return f"{first} {last_init}.".strip() if first else None


@router.post("/submit", response_model=ReviewSubmitResponse)
async def submit_review(
    payload: ReviewSubmitRequest,
    current_user: User = Depends(get_current_student),
    db: Session = Depends(get_db),
    service: ReviewService = Depends(get_review_service),
):
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

        # If tip provided, create a standalone PaymentIntent for the tip
        if payload.tip_amount_cents and payload.tip_amount_cents > 0:
            try:
                stripe_service = StripeService(db)
                customer = stripe_service.get_or_create_customer(current_user.id)
                instr_repo = InstructorProfileRepository(db)
                instructor_profile = instr_repo.get_by_user_id(review.instructor_id)
                if not instructor_profile:
                    raise HTTPException(status_code=400, detail="Instructor profile not found for tip")
                connected = stripe_service.payment_repository.get_connected_account_by_instructor_id(  # type: ignore[attr-defined]
                    instructor_profile.id
                )
                if not connected or not connected.stripe_account_id:
                    raise HTTPException(status_code=400, detail="Instructor is not set up to receive tips")

                # Create PaymentIntent for the tip as a destination charge
                pi_record = stripe_service.create_payment_intent(
                    booking_id=review.booking_id,
                    customer_id=customer.stripe_customer_id,
                    destination_account_id=connected.stripe_account_id,
                    amount_cents=int(payload.tip_amount_cents),
                )

                # Try auto-confirm with student's default payment method
                default_pm = stripe_service.payment_repository.get_default_payment_method(current_user.id)
                if default_pm and default_pm.stripe_payment_method_id:
                    try:
                        pi_after_confirm = stripe_service.confirm_payment_intent(
                            pi_record.stripe_payment_intent_id, default_pm.stripe_payment_method_id
                        )
                        tip_status = pi_after_confirm.status
                        # If further action required (SCA), provide client_secret for client-side confirmation
                        if tip_status in ("requires_action", "requires_confirmation"):
                            try:
                                import stripe as _stripe

                                if getattr(stripe_service, "stripe_configured", False):
                                    pi = _stripe.PaymentIntent.retrieve(pi_record.stripe_payment_intent_id)
                                    tip_client_secret = getattr(pi, "client_secret", None)
                            except Exception:
                                tip_client_secret = None
                    except Exception:
                        # If confirm failed, allow client to attempt confirmation if possible
                        tip_status = "requires_payment_method"
                        tip_client_secret = None
                else:
                    # No default payment method; client would need to add one to complete tip
                    tip_status = "requires_payment_method"
                    tip_client_secret = None
            except HTTPException:
                raise
            except Exception:
                # Non-blocking; allow review submission even if tip intent fails
                tip_status = "failed"
                tip_client_secret = None

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


@router.get("/instructor/{instructor_id}/ratings", response_model=InstructorRatingsResponse)
def get_instructor_ratings(
    instructor_id: str,
    service: ReviewService = Depends(get_review_service),
):
    return InstructorRatingsResponse(**service.get_instructor_ratings(instructor_id))


@router.get("/instructor/{instructor_id}/search-rating", response_model=SearchRatingResponse)
def get_search_rating(
    instructor_id: str,
    instructor_service_id: Optional[str] = Query(None),
    service: ReviewService = Depends(get_review_service),
):
    return SearchRatingResponse(**service.get_rating_for_search_context(instructor_id, instructor_service_id))


@router.get("/instructor/{instructor_id}/recent", response_model=ReviewListPageResponse)
def get_recent_reviews(
    instructor_id: str,
    instructor_service_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    with_text: Optional[bool] = Query(None),
    service: ReviewService = Depends(get_review_service),
):
    reviews = service.get_recent_reviews(
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        limit=limit,
        page=page,
        min_rating=min_rating,
        with_text=with_text,
    )
    total = service.count_recent_reviews(
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        min_rating=min_rating,
        with_text=with_text,
    )
    items: list[ReviewItem] = []
    for r in reviews:
        reviewer_name = None
        try:
            from ..models.user import User as _User

            user = service.db.query(_User).filter(_User.id == r.student_id).first()  # type: ignore[attr-defined]
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


@router.get("/booking/{booking_id}", response_model=Optional[ReviewItem])
def get_review_for_booking(
    booking_id: str,
    current_user: User = Depends(get_current_student),
    service: ReviewService = Depends(get_review_service),
):
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


@router.post("/booking/existing", response_model=list[str])
def get_existing_reviews_for_bookings(
    booking_ids: list[str],
    current_user: User = Depends(get_current_student),
    service: ReviewService = Depends(get_review_service),
):
    # Enforce ownership: inject current_student_id into session for service-level guard,
    # and pre-filter ids by ownership using booking repository
    try:
        setattr(service.db, "current_student_id", current_user.id)
    except Exception:
        pass
    from ..repositories.booking_repository import BookingRepository

    owner_repo = BookingRepository(service.db)
    owned_ids = owner_repo.filter_owned_booking_ids(booking_ids, current_user.id)
    if not owned_ids:
        return []
    return service.get_existing_reviews_for_bookings(owned_ids)


@router.post("/reviews/{review_id}/respond", response_model=ReviewResponseModel)
def respond_to_review(
    review_id: str,
    response_text: str,
    current_user: User = Depends(get_current_active_user),
    service: ReviewService = Depends(get_review_service),
):
    # Must be instructor owner of the review
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


@router.post("/ratings/batch", response_model=RatingsBatchResponse)
def get_ratings_batch(
    payload: RatingsBatchRequest,
    service: ReviewService = Depends(get_review_service),
):
    instructor_ids = payload.instructor_ids
    results = []
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
