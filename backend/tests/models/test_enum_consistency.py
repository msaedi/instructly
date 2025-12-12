# backend/tests/models/test_enum_consistency.py
"""
Enum consistency tests to prevent silent ORM/database mismatches.

This test module catches the bug discovered on Dec 7 2024 where:
- Bulk SQL seeding used lowercase enum values ('published')
- SQLAlchemy SAEnum defaulted to uppercase names ('PUBLISHED')
- Result: No errors thrown, but ORM queries returned zero results

These tests verify:
1. Enum values round-trip correctly through the database
2. Raw SQL inserts are queryable via ORM
3. Enum definitions follow safe patterns
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
import ulid

from app.models import Booking, BookingStatus
from app.models.base_enum import verify_enum_consistency
from app.models.event_outbox import EventOutbox, EventOutboxStatus
from app.models.referrals import (
    ReferralCode,
    ReferralCodeStatus,
    RewardSide,
    RewardStatus,
    WalletTransactionType,
)
from app.models.review import Review, ReviewStatus


class TestEnumDefinitionSafety:
    """Verify enum classes follow safe patterns."""

    @pytest.mark.parametrize(
        "enum_class",
        [
            ReviewStatus,
            ReferralCodeStatus,
            RewardSide,
            RewardStatus,
            WalletTransactionType,
            BookingStatus,
            EventOutboxStatus,
        ],
    )
    def test_enum_inherits_from_str(self, enum_class: type) -> None:
        """All database enums must inherit from str for safe comparison."""
        assert issubclass(
            enum_class, str
        ), f"{enum_class.__name__} must inherit from (str, Enum)"

    @pytest.mark.parametrize(
        "enum_class",
        [
            ReviewStatus,
            ReferralCodeStatus,
            RewardSide,
            RewardStatus,
            WalletTransactionType,
        ],
    )
    def test_enum_consistency_verification(self, enum_class: type) -> None:
        """Verify enum passes our consistency check."""
        # Should not raise
        verify_enum_consistency(enum_class)


class TestSAEnumRoundTrip:
    """Test that SAEnum columns correctly round-trip through the database."""

    def test_review_status_orm_insert_raw_query(
        self, db: Session, test_booking: Booking
    ) -> None:
        """
        Insert via ORM, verify raw SQL sees the correct value.
        This catches the case where SAEnum stores NAME instead of VALUE.
        """
        # Create review via ORM
        review = Review(
            booking_id=test_booking.id,
            student_id=test_booking.student_id,
            instructor_id=test_booking.instructor_id,
            instructor_service_id=test_booking.instructor_service_id,
            rating=5,
            status=ReviewStatus.PUBLISHED,
            booking_completed_at=datetime.now(timezone.utc),
        )
        db.add(review)
        db.flush()

        # Query via raw SQL to see actual DB value
        result = db.execute(
            text("SELECT status FROM reviews WHERE id = :id"), {"id": review.id}
        ).fetchone()

        assert result is not None
        db_value = result[0]

        # CRITICAL: DB should contain 'published' (value), not 'PUBLISHED' (name)
        assert db_value == ReviewStatus.PUBLISHED.value, (
            f"Enum mismatch: ORM inserted '{db_value}', "
            f"expected '{ReviewStatus.PUBLISHED.value}' (enum value). "
            "Check SAEnum values_callable configuration."
        )

    def test_review_status_raw_insert_orm_query(
        self, db: Session, test_booking: Booking
    ) -> None:
        """
        Insert via raw SQL, verify ORM can query it.
        This is the EXACT bug from Dec 7 2024 - bulk SQL used lowercase,
        ORM expected uppercase, queries returned zero results.
        """
        review_id = str(ulid.ULID())

        # Insert using raw SQL with lowercase value (like bulk seeding does)
        db.execute(
            text(
                """
                INSERT INTO reviews (
                    id, booking_id, student_id, instructor_id,
                    instructor_service_id, rating, status, booking_completed_at, created_at
                )
                VALUES (
                    :id, :booking_id, :student_id, :instructor_id,
                    :instructor_service_id, :rating, 'published', :completed_at, :created_at
                )
                """
            ),
            {
                "id": review_id,
                "booking_id": test_booking.id,
                "student_id": test_booking.student_id,
                "instructor_id": test_booking.instructor_id,
                "instructor_service_id": test_booking.instructor_service_id,
                "rating": 5,
                "completed_at": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
            },
        )
        db.commit()

        # Now query via ORM - this is where the Dec 7 bug manifested
        reviews = (
            db.query(Review).filter(Review.status == ReviewStatus.PUBLISHED).all()
        )

        matching = [r for r in reviews if r.id == review_id]
        assert len(matching) == 1, (
            "ORM cannot find record inserted via raw SQL. "
            "This is the Dec 7 2024 bug - SAEnum values_callable is not configured. "
            f"Raw SQL used 'published', ORM query used {ReviewStatus.PUBLISHED}."
        )

    def test_review_all_status_values_documented(self) -> None:
        """Document all ReviewStatus values for reference and verify consistency."""
        # Verify all status values match their expected lowercase pattern
        expected = {
            "PUBLISHED": "published",
            "FLAGGED": "flagged",
            "HIDDEN": "hidden",
            "REMOVED": "removed",
        }
        for name, value in expected.items():
            member = ReviewStatus[name]
            assert member.value == value, (
                f"ReviewStatus.{name} has value '{member.value}', expected '{value}'. "
                "Enum value changed - check if bulk SQL seeding needs update."
            )


class TestReferralEnumRoundTrip:
    """Test referral-related enum columns."""

    def test_referral_code_status_round_trip(
        self, db: Session, test_student: "User"
    ) -> None:
        """Verify ReferralCodeStatus round-trips correctly."""
        code = ReferralCode(
            code="TEST123",
            referrer_user_id=test_student.id,
            status=ReferralCodeStatus.ACTIVE,
        )
        db.add(code)
        db.flush()

        # Verify raw SQL value
        result = db.execute(
            text("SELECT status FROM referral_codes WHERE code = :code"),
            {"code": "TEST123"},
        ).fetchone()

        assert result is not None
        assert result[0] == "active", (
            f"Expected 'active' in DB, got '{result[0]}'. "
            "SAEnum storing enum names instead of values."
        )

        # Verify ORM query works
        queried = (
            db.query(ReferralCode)
            .filter(ReferralCode.status == ReferralCodeStatus.ACTIVE)
            .filter(ReferralCode.code == "TEST123")
            .first()
        )
        assert queried is not None


class TestBookingStatusConsistency:
    """
    Test BookingStatus consistency.

    Note: Booking uses String column, not SAEnum, so enum values are stored
    as-is. This tests that the string storage matches expectations.
    """

    def test_booking_status_string_storage(
        self, db: Session, test_booking: Booking
    ) -> None:
        """Verify BookingStatus values are stored correctly as strings."""
        # Use existing test_booking fixture (already has CONFIRMED status)
        # Check raw value
        result = db.execute(
            text("SELECT status FROM bookings WHERE id = :id"), {"id": test_booking.id}
        ).fetchone()

        assert result is not None
        # BookingStatus uses uppercase values
        assert result[0] == "CONFIRMED", (
            f"Expected 'CONFIRMED' in DB, got '{result[0]}'. "
            "BookingStatus enum values may have changed."
        )

    def test_booking_status_all_values(self) -> None:
        """Document all BookingStatus values for reference."""
        expected = {
            "PENDING": "PENDING",
            "CONFIRMED": "CONFIRMED",
            "COMPLETED": "COMPLETED",
            "CANCELLED": "CANCELLED",
            "NO_SHOW": "NO_SHOW",
        }
        for name, value in expected.items():
            member = BookingStatus[name]
            assert member.value == value, (
                f"BookingStatus.{name} has value '{member.value}', expected '{value}'"
            )


class TestEventOutboxStatusConsistency:
    """Test EventOutboxStatus string storage."""

    def test_event_outbox_status_storage(self, db: Session) -> None:
        """Verify EventOutboxStatus values are stored correctly."""
        event = EventOutbox(
            event_type="test_event",
            aggregate_id="test_agg_123",
            idempotency_key=f"test_idem_{ulid.ULID()}",
            payload={"test": "data"},
            status=EventOutboxStatus.PENDING.value,
        )
        db.add(event)
        db.flush()

        result = db.execute(
            text("SELECT status FROM event_outbox WHERE id = :id"), {"id": event.id}
        ).fetchone()

        assert result is not None
        assert result[0] == "PENDING"


class TestSeededDataAccessibility:
    """
    Verify that seeded data is accessible via ORM.

    These tests use the existing seeded data to verify no enum mismatches.
    """

    def test_orm_finds_all_published_reviews(self, db: Session) -> None:
        """
        ORM count should match raw SQL count for published reviews.
        A mismatch indicates enum value inconsistency.
        """
        orm_count = (
            db.query(Review).filter(Review.status == ReviewStatus.PUBLISHED).count()
        )
        raw_count = db.execute(
            text("SELECT COUNT(*) FROM reviews WHERE status = 'published'")
        ).scalar()

        # If ORM count is 0 but raw count is > 0, we have the Dec 7 bug
        if raw_count and raw_count > 0:
            assert orm_count == raw_count, (
                f"ORM found {orm_count} published reviews but DB has {raw_count}. "
                "This indicates enum value mismatch - the Dec 7 2024 bug."
            )

    def test_orm_finds_all_confirmed_bookings(self, db: Session) -> None:
        """
        ORM count should match raw SQL count for confirmed bookings.
        """
        orm_count = db.query(Booking).filter(Booking.status == "CONFIRMED").count()
        raw_count = db.execute(
            text("SELECT COUNT(*) FROM bookings WHERE status = 'CONFIRMED'")
        ).scalar()

        if raw_count and raw_count > 0:
            assert orm_count == raw_count, (
                f"ORM found {orm_count} confirmed bookings but DB has {raw_count}. "
                "Check booking status string values."
            )
