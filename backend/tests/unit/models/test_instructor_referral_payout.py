"""Tests for InstructorReferralPayout model."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.fixtures.unique_test_data import unique_data

from app.auth import get_password_hash
from app.core.enums import RoleName
from app.models.instructor import InstructorProfile
from app.models.referrals import InstructorReferralPayout
from app.models.user import User
from app.services.permission_service import PermissionService


def _create_instructor(db: Session, *, email: str, password: str) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        first_name="Test",
        last_name="Instructor",
        zip_code="10001",
        is_active=True,
    )
    db.add(user)
    db.flush()

    permission_service = PermissionService(db)
    permission_service.assign_role(user.id, RoleName.INSTRUCTOR)

    profile = InstructorProfile(user_id=user.id)
    db.add(profile)
    db.flush()

    return user


class TestInstructorReferralPayoutModel:
    """Tests for InstructorReferralPayout database model."""

    def test_create_payout_with_required_fields(
        self, db: Session, test_instructor: User, test_instructor_2: User, test_booking
    ) -> None:
        """Test creating a payout record with all required fields."""
        payout = InstructorReferralPayout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=f"test_payout_{unique_data.unique_slug('payout')}",
        )

        db.add(payout)
        db.flush()

        assert payout.id is not None
        assert len(payout.id) == 26
        assert payout.stripe_transfer_status == "pending"
        assert payout.created_at is not None

    def test_unique_referred_instructor_constraint(
        self, db: Session, test_instructor: User, test_instructor_2: User, test_booking
    ) -> None:
        """Test that only one payout per referred instructor is allowed."""
        payout1 = InstructorReferralPayout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=f"payout1_{unique_data.unique_slug('payout')}",
        )
        db.add(payout1)
        db.flush()

        payout2 = InstructorReferralPayout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=f"payout2_{unique_data.unique_slug('payout')}",
        )
        db.add(payout2)

        with pytest.raises(IntegrityError):
            db.flush()

    def test_idempotency_key_unique_constraint(
        self,
        db: Session,
        test_password: str,
        test_instructor: User,
        test_instructor_2: User,
        test_booking,
    ) -> None:
        """Test idempotency key uniqueness constraint."""
        referrer = test_instructor
        referred1 = test_instructor_2
        referred2 = _create_instructor(
            db, email=unique_data.unique_email("instructor3"), password=test_password
        )

        idempotency_key = f"same_key_{unique_data.unique_slug('payout')}"

        payout1 = InstructorReferralPayout(
            referrer_user_id=referrer.id,
            referred_instructor_id=referred1.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=idempotency_key,
        )
        db.add(payout1)
        db.flush()

        payout2 = InstructorReferralPayout(
            referrer_user_id=referrer.id,
            referred_instructor_id=referred2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=5000,
            was_founding_bonus=False,
            idempotency_key=idempotency_key,
        )
        db.add(payout2)

        with pytest.raises(IntegrityError):
            db.flush()

    def test_payout_relationships(
        self, db: Session, test_instructor: User, test_instructor_2: User, test_booking
    ) -> None:
        """Test referrer, referred_instructor, and triggering_booking relationships."""
        payout = InstructorReferralPayout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=f"rel_test_{unique_data.unique_slug('payout')}",
        )
        db.add(payout)
        db.flush()

        assert payout.referrer.id == test_instructor.id
        assert payout.referred_instructor.id == test_instructor_2.id
        assert payout.triggering_booking.id == test_booking.id

    def test_payout_status_default(
        self, db: Session, test_instructor: User, test_instructor_2: User, test_booking
    ) -> None:
        """Test that new payouts default to pending status."""
        payout = InstructorReferralPayout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=f"status_test_{unique_data.unique_slug('payout')}",
        )
        db.add(payout)
        db.flush()

        assert payout.stripe_transfer_status == "pending"
        assert payout.stripe_transfer_id is None
        assert payout.transferred_at is None
        assert payout.failed_at is None
        assert payout.failure_reason is None

    def test_payout_amounts(
        self,
        db: Session,
        test_password: str,
        test_instructor: User,
        test_instructor_2: User,
        test_booking,
    ) -> None:
        """Test founding ($75) vs standard ($50) bonus amounts."""
        referred2 = _create_instructor(
            db, email=unique_data.unique_email("instructor4"), password=test_password
        )

        payout_founding = InstructorReferralPayout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=f"founding_{unique_data.unique_slug('payout')}",
        )
        db.add(payout_founding)
        db.flush()

        assert payout_founding.amount_cents == 7500
        assert payout_founding.was_founding_bonus is True

        payout_standard = InstructorReferralPayout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=referred2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=5000,
            was_founding_bonus=False,
            idempotency_key=f"standard_{unique_data.unique_slug('payout')}",
        )
        db.add(payout_standard)
        db.flush()

        assert payout_standard.amount_cents == 5000
        assert payout_standard.was_founding_bonus is False
