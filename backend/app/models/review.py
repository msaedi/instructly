# backend/app/models/review.py
"""
Reviews & Ratings models for InstaInstru.

Design notes:
- ULID string IDs everywhere (26 chars)
- Timezone-aware timestamps
- Review is per booking (one review per booking via DB unique constraint)
- Service-level linkage uses instructor_service_id (what was booked)
- Moderation handled via status enum; hidden/removed are excluded from display/aggregation
"""

from datetime import datetime, timezone
from enum import Enum

import ulid
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class ReviewStatus(str, Enum):
    """Publication state for a review."""

    PUBLISHED = "published"
    FLAGGED = "flagged"
    HIDDEN = "hidden"
    REMOVED = "removed"


class Review(Base):
    """
    Per-booking review submitted by a student.
    """

    __tablename__ = "reviews"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Relationships
    booking_id = Column(String(26), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, unique=True)
    student_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    instructor_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    instructor_service_id = Column(
        String(26), ForeignKey("instructor_services.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Rating data
    rating = Column(Integer, nullable=False)
    review_text = Column(Text, nullable=True)

    # Moderation & verification
    status = Column(SAEnum(ReviewStatus, name="review_status"), nullable=False, default=ReviewStatus.PUBLISHED)
    is_verified = Column(Boolean, nullable=False, default=False, comment="Student attended the session")

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    booking_completed_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships (optional backrefs)
    response = relationship("ReviewResponse", uselist=False, back_populates="review", cascade="all, delete-orphan")
    tip = relationship("ReviewTip", uselist=False, back_populates="review", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_reviews_booking"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        CheckConstraint(
            "(review_text IS NULL) OR (length(review_text) <= 500)",
            name="ck_reviews_text_length",
        ),
        Index("idx_reviews_instructor", "instructor_id"),
        Index("idx_reviews_instructor_service", "instructor_id", "instructor_service_id"),
        Index("idx_reviews_created_at", "created_at"),
    )


class ReviewResponse(Base):
    """Single instructor reply to a review."""

    __tablename__ = "review_responses"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    review_id = Column(String(26), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, unique=True)
    instructor_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    response_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    review = relationship("Review", back_populates="response")

    __table_args__ = (
        CheckConstraint(
            "(response_text IS NULL) OR (length(response_text) <= 500)",
            name="ck_review_responses_text_length",
        ),
        Index("idx_review_responses_review", "review_id"),
    )


class ReviewTip(Base):
    """Optional tip attached to a review, processed via Stripe."""

    __tablename__ = "review_tips"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    review_id = Column(String(26), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, unique=True)
    amount_cents = Column(Integer, nullable=False)
    stripe_payment_intent_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending, completed, failed
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime(timezone=True), nullable=True)

    review = relationship("Review", back_populates="tip")

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_review_tips_positive"),
        Index("idx_review_tips_review", "review_id"),
        Index("idx_review_tips_status", "status"),
    )
