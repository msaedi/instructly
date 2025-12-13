# backend/app/routes/reviews.py
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..api.dependencies.auth import get_current_active_user, get_current_student
from ..core.exceptions import DomainException
from ..database import get_db
from ..models.user import User
from ..schemas.review import (
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
from ..services.review_service import ReviewService

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
    payload: ReviewSubmitRequest = Body(...),
    current_user: User = Depends(get_current_student),
    service: ReviewService = Depends(get_review_service),
) -> ReviewSubmitResponse:
    try:
        result = await asyncio.to_thread(
            service.submit_review_with_tip,
            student_id=current_user.id,
            booking_id=payload.booking_id,
            rating=payload.rating,
            review_text=payload.review_text,
            tip_amount_cents=payload.tip_amount_cents,
        )
        review = result["review"]
        return ReviewSubmitResponse(
            id=review.id,
            rating=review.rating,
            review_text=review.review_text,
            created_at=review.created_at,
            instructor_service_id=review.instructor_service_id,
            reviewer_display_name=_display_name(current_user),
            tip_status=result.get("tip_status"),
            tip_client_secret=result.get("tip_client_secret"),
        )
    except DomainException as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/instructor/{instructor_id}/ratings", response_model=InstructorRatingsResponse)
def get_instructor_ratings(
    instructor_id: str,
    service: ReviewService = Depends(get_review_service),
) -> InstructorRatingsResponse:
    return InstructorRatingsResponse(**service.get_instructor_ratings(instructor_id))


@router.get("/instructor/{instructor_id}/search-rating", response_model=SearchRatingResponse)
def get_search_rating(
    instructor_id: str,
    instructor_service_id: Optional[str] = Query(None),
    service: ReviewService = Depends(get_review_service),
) -> SearchRatingResponse:
    return SearchRatingResponse(
        **service.get_rating_for_search_context(instructor_id, instructor_service_id)
    )


@router.get("/instructor/{instructor_id}/recent", response_model=ReviewListPageResponse)
def get_recent_reviews(
    instructor_id: str,
    instructor_service_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    rating: Optional[int] = Query(None, ge=1, le=5),
    with_text: Optional[bool] = Query(None),
    service: ReviewService = Depends(get_review_service),
) -> ReviewListPageResponse:
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
            from ..models.user import User as _User

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


@router.get("/booking/{booking_id}", response_model=Optional[ReviewItem])
def get_review_for_booking(
    booking_id: str,
    current_user: User = Depends(get_current_student),
    service: ReviewService = Depends(get_review_service),
) -> Optional[ReviewItem]:
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


@router.post("/booking/existing", response_model=ExistingReviewIdsResponse)
def get_existing_reviews_for_bookings(
    booking_ids: List[str],
    current_user: User = Depends(get_current_student),
    service: ReviewService = Depends(get_review_service),
) -> ExistingReviewIdsResponse:
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
        return ExistingReviewIdsResponse([])
    review_ids = service.get_existing_reviews_for_bookings(owned_ids)
    return ExistingReviewIdsResponse([str(rid) for rid in review_ids])


@router.post("/reviews/{review_id}/respond", response_model=ReviewResponseModel)
def respond_to_review(
    review_id: str,
    response_text: str,
    current_user: User = Depends(get_current_active_user),
    service: ReviewService = Depends(get_review_service),
) -> ReviewResponseModel:
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
    payload: RatingsBatchRequest = Body(...),
    service: ReviewService = Depends(get_review_service),
) -> RatingsBatchResponse:
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
