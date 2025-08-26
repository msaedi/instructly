# backend/app/repositories/review_repository.py
"""
Repositories for reviews/ratings system.

Follows repository pattern: no business logic, DB-only operations.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..core.exceptions import NotFoundException, RepositoryException
from ..models.review import Review, ReviewResponse, ReviewStatus, ReviewTip
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ReviewRepository(BaseRepository[Review]):
    """Data access for `Review`."""

    def __init__(self, db: Session):
        super().__init__(db, Review)
        self.logger = logging.getLogger(__name__)

    def create_review(self, **kwargs) -> Review:
        try:
            review = Review(**kwargs)
            self.db.add(review)
            self.db.flush()
            return review
        except Exception as e:
            self.logger.error(f"Error creating review: {e}")
            raise RepositoryException(f"Failed to create review: {e}")

    def exists_for_booking(self, booking_id: str) -> bool:
        try:
            return self.db.query(self.model.id).filter(self.model.booking_id == booking_id).first() is not None
        except Exception as e:
            self.logger.error(f"Error checking review existence: {e}")
            raise RepositoryException(f"Failed to check review existence: {e}")

    def get_by_booking_id(self, booking_id: str) -> Optional[Review]:
        try:
            return self.db.query(Review).filter(Review.booking_id == booking_id).first()
        except Exception as e:
            self.logger.error(f"Error fetching review by booking: {e}")
            raise RepositoryException(f"Failed to fetch review by booking: {e}")

    def get_instructor_aggregates(self, instructor_id: str) -> Dict:
        """Return total count and sum for published/flagged reviews (exclude hidden/removed)."""
        try:
            q = self.db.query(
                func.count(Review.id).label("total_reviews"),
                func.avg(Review.rating * 1.0).label("raw_average"),
                func.sum(Review.rating).label("rating_sum"),
            ).filter(
                and_(
                    Review.instructor_id == instructor_id,
                    Review.status.in_([ReviewStatus.PUBLISHED.value, ReviewStatus.FLAGGED.value]),
                )
            )
            row = q.first()
            if not row:
                return {"total_reviews": 0, "raw_average": 0.0, "rating_sum": 0}
            return {
                "total_reviews": int(row.total_reviews or 0),
                "raw_average": float(row.raw_average or 0.0),
                "rating_sum": int(row.rating_sum or 0),
            }
        except Exception as e:
            self.logger.error(f"Error aggregating instructor reviews: {e}")
            raise RepositoryException(f"Failed to aggregate reviews: {e}")

    def get_service_aggregates(self, instructor_id: str, instructor_service_id: str) -> Dict:
        try:
            q = self.db.query(
                func.count(Review.id).label("review_count"),
                func.avg(Review.rating * 1.0).label("raw_average"),
                func.sum(Review.rating).label("rating_sum"),
            ).filter(
                and_(
                    Review.instructor_id == instructor_id,
                    Review.instructor_service_id == instructor_service_id,
                    Review.status.in_([ReviewStatus.PUBLISHED.value, ReviewStatus.FLAGGED.value]),
                )
            )
            row = q.first()
            if not row:
                return {"review_count": 0, "raw_average": 0.0, "rating_sum": 0}
            return {
                "review_count": int(row.review_count or 0),
                "raw_average": float(row.raw_average or 0.0),
                "rating_sum": int(row.rating_sum or 0),
            }
        except Exception as e:
            self.logger.error(f"Error aggregating service reviews: {e}")
            raise RepositoryException(f"Failed to aggregate service reviews: {e}")

    def get_service_breakdown(self, instructor_id: str) -> List[Dict]:
        try:
            # Aggregate by instructor_service_id
            rows = (
                self.db.query(
                    Review.instructor_service_id.label("instructor_service_id"),
                    func.count(Review.id).label("review_count"),
                    func.avg(Review.rating * 1.0).label("raw_average"),
                    func.sum(Review.rating).label("rating_sum"),
                )
                .filter(
                    and_(
                        Review.instructor_id == instructor_id,
                        Review.status.in_([ReviewStatus.PUBLISHED.value, ReviewStatus.FLAGGED.value]),
                    )
                )
                .group_by(Review.instructor_service_id)
                .all()
            )
            return [
                {
                    "instructor_service_id": r.instructor_service_id,
                    "review_count": int(r.review_count or 0),
                    "raw_average": float(r.raw_average or 0.0),
                    "rating_sum": int(r.rating_sum or 0),
                }
                for r in rows
            ]
        except Exception as e:
            self.logger.error(f"Error getting service breakdown: {e}")
            raise RepositoryException(f"Failed to get service breakdown: {e}")

    def _apply_recent_filters(
        self,
        q,
        *,
        instructor_id: str,
        instructor_service_id: Optional[str] = None,
        min_rating: Optional[int] = None,
        with_text: Optional[bool] = None,
    ):
        q = q.filter(
            and_(
                Review.instructor_id == instructor_id,
                Review.status == ReviewStatus.PUBLISHED.value,
            )
        )
        if instructor_service_id:
            q = q.filter(Review.instructor_service_id == instructor_service_id)
        if min_rating is not None:
            q = q.filter(Review.rating >= int(min_rating))
        if with_text is True:
            q = q.filter(func.length(func.trim(func.coalesce(Review.review_text, ""))) > 0)
        return q

    def get_recent_reviews(
        self,
        instructor_id: str,
        instructor_service_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        *,
        min_rating: Optional[int] = None,
        with_text: Optional[bool] = None,
    ) -> List[Review]:
        try:
            q = self.db.query(Review)
            q = self._apply_recent_filters(
                q,
                instructor_id=instructor_id,
                instructor_service_id=instructor_service_id,
                min_rating=min_rating,
                with_text=with_text,
            )
            return q.order_by(Review.created_at.desc()).offset(offset).limit(limit).all()
        except Exception as e:
            self.logger.error(f"Error getting recent reviews: {e}")
            raise RepositoryException(f"Failed to get recent reviews: {e}")

    def count_recent_reviews(
        self,
        instructor_id: str,
        instructor_service_id: Optional[str] = None,
        *,
        min_rating: Optional[int] = None,
        with_text: Optional[bool] = None,
    ) -> int:
        try:
            q = self.db.query(func.count(Review.id))
            q = self._apply_recent_filters(
                q,
                instructor_id=instructor_id,
                instructor_service_id=instructor_service_id,
                min_rating=min_rating,
                with_text=with_text,
            )
            return int(q.scalar() or 0)
        except Exception as e:
            self.logger.error(f"Error counting recent reviews: {e}")
            raise RepositoryException(f"Failed to count recent reviews: {e}")

    def get_existing_for_bookings(self, booking_ids: List[str]) -> List[str]:
        """Return booking IDs that already have a review (published/flagged/hidden/removed all count)."""
        try:
            rows = self.db.query(Review.booking_id).filter(Review.booking_id.in_(booking_ids)).all()
            return [r[0] if isinstance(r, tuple) else r.booking_id for r in rows]
        except Exception as e:
            self.logger.error(f"Error checking existing reviews for bookings: {e}")
            raise RepositoryException(f"Failed to check existing reviews: {e}")

    def get_published_verified_for_instructor(
        self, instructor_id: str, instructor_service_id: Optional[str] = None
    ) -> List[Review]:
        """Return published/flagged, verified reviews for an instructor (optionally by service).

        Used for computing weighted histograms and Bayesian/Dirichlet smoothed ratings in service layer.
        """
        try:
            q = self.db.query(Review).filter(
                and_(
                    Review.instructor_id == instructor_id,
                    Review.is_verified.is_(True),
                    Review.status.in_([ReviewStatus.PUBLISHED.value, ReviewStatus.FLAGGED.value]),
                )
            )
            if instructor_service_id:
                q = q.filter(Review.instructor_service_id == instructor_service_id)
            return q.all()
        except Exception as e:
            self.logger.error(f"Error fetching verified reviews for instructor: {e}")
            raise RepositoryException(f"Failed to fetch verified reviews: {e}")


class ReviewResponseRepository(BaseRepository[ReviewResponse]):
    """Data access for `ReviewResponse`."""

    def __init__(self, db: Session):
        super().__init__(db, ReviewResponse)

    def create_response(self, **kwargs) -> ReviewResponse:
        try:
            response = ReviewResponse(**kwargs)
            self.db.add(response)
            self.db.flush()
            return response
        except Exception as e:
            raise RepositoryException(f"Failed to create review response: {e}")

    def exists_for_review(self, review_id: str) -> bool:
        try:
            return self.db.query(self.model.id).filter(self.model.review_id == review_id).first() is not None
        except Exception as e:
            raise RepositoryException(f"Failed to check response existence: {e}")


class ReviewTipRepository(BaseRepository[ReviewTip]):
    """Data access for `ReviewTip`."""

    def __init__(self, db: Session):
        super().__init__(db, ReviewTip)

    def create_tip(self, **kwargs) -> ReviewTip:
        try:
            tip = ReviewTip(**kwargs)
            self.db.add(tip)
            self.db.flush()
            return tip
        except Exception as e:
            raise RepositoryException(f"Failed to create review tip: {e}")

    def update_tip_status(self, tip_id: str, status: str, processed_at=None) -> Optional[ReviewTip]:
        try:
            tip = self.db.query(ReviewTip).filter(ReviewTip.id == tip_id).first()
            if not tip:
                return None
            tip.status = status
            if processed_at is not None:
                tip.processed_at = processed_at
            return tip
        except Exception as e:
            raise RepositoryException(f"Failed to update tip status: {e}")
