"""
Integration tests for the complete instructor referral flow.

Covers the journey from referral attribution to payout creation and API responses.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.models.referrals import InstructorReferralPayout, ReferralAttribution
from app.models.service_catalog import InstructorService, ServiceCatalog
from app.models.user import User
from app.repositories.referral_repository import ReferralRewardRepository
from app.services.referral_service import ReferralService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.factories.booking_builders import create_booking_pg_safe
    from backend.tests.fixtures.unique_test_data import unique_data
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe
    from tests.fixtures.unique_test_data import unique_data


def _get_instructor_profile(db: Session, user_id: str) -> InstructorProfile:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first()
    assert profile is not None
    return profile


def _ensure_stripe_connected_account(db: Session, profile: InstructorProfile) -> StripeConnectedAccount:
    existing = (
        db.query(StripeConnectedAccount)
        .filter(StripeConnectedAccount.instructor_profile_id == profile.id)
        .first()
    )
    if existing:
        return existing

    account = StripeConnectedAccount(
        instructor_profile_id=profile.id,
        stripe_account_id=f"acct_{unique_data.unique_slug('referral')}",
        onboarding_completed=True,
    )
    db.add(account)
    db.flush()
    return account


def _get_instructor_service(db: Session, profile: InstructorProfile) -> InstructorService:
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active.is_(True),
        )
        .first()
    )
    if service is not None:
        return service

    catalog = db.query(ServiceCatalog).order_by(ServiceCatalog.slug).first()
    assert catalog is not None

    service = InstructorService(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=75.0,
        duration_options=[60],
        is_active=True,
    )
    db.add(service)
    db.flush()
    return service


def _create_completed_booking(
    db: Session,
    *,
    instructor: User,
    student: User,
    offset_index: int = 0,
) -> tuple[str, datetime]:
    profile = _get_instructor_profile(db, instructor.id)
    service = _get_instructor_service(db, profile)
    booking_date = date.today()
    start_time = time(10, 0)
    end_time = time(11, 0)
    completed_at = datetime.now(timezone.utc)

    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=BookingStatus.COMPLETED,
        offset_index=offset_index,
        service_name=service.catalog_entry.name if service.catalog_entry else "Test Service",
        hourly_rate=float(service.hourly_rate),
        total_price=float(service.hourly_rate),
        duration_minutes=60,
        completed_at=completed_at,
    )

    return booking.id, completed_at


class TestInstructorReferralFullFlow:
    """Test the complete referral flow from attribution to payout."""

    def test_full_referral_flow_founding_phase(
        self,
        db: Session,
        test_instructor: User,
        test_instructor_2: User,
        test_student: User,
    ) -> None:
        """First completed lesson during founding phase creates a $75 payout."""
        referrer = test_instructor
        referred = test_instructor_2

        referrer_profile = _get_instructor_profile(db, referrer.id)
        _ensure_stripe_connected_account(db, referrer_profile)

        referred_profile = _get_instructor_profile(db, referred.id)
        referred_profile.is_live = True
        referred_profile.bgc_status = "passed"
        referred_profile.onboarding_completed_at = datetime.now(timezone.utc)

        referral_service = ReferralService(db)
        code = referral_service.ensure_code_for_user(referrer.id)

        attribution = ReferralAttribution(
            code_id=code.id,
            referred_user_id=referred.id,
            source="test",
            ts=datetime.now(timezone.utc),
        )
        db.add(attribution)
        db.flush()

        booking_id, completed_at = _create_completed_booking(
            db, instructor=referred, student=test_student
        )

        with patch("app.services.referral_service.enqueue_task"):
            payout_id = referral_service.on_instructor_lesson_completed(
                instructor_user_id=referred.id,
                booking_id=booking_id,
                completed_at=completed_at,
            )

        referral_repo = ReferralRewardRepository(db)
        payout = referral_repo.get_instructor_referral_payout_by_referred(referred.id)

        assert payout is not None
        assert payout_id == payout.id
        assert payout.referrer_user_id == referrer.id
        assert payout.referred_instructor_id == referred.id
        assert payout.amount_cents == 7500
        assert payout.was_founding_bonus is True
        assert payout.stripe_transfer_status == "pending"

    def test_second_lesson_does_not_create_duplicate_payout(
        self,
        db: Session,
        test_instructor: User,
        test_instructor_2: User,
        test_student: User,
    ) -> None:
        """Second completed lesson does not create another payout."""
        referrer = test_instructor
        referred = test_instructor_2

        referrer_profile = _get_instructor_profile(db, referrer.id)
        _ensure_stripe_connected_account(db, referrer_profile)

        referral_service = ReferralService(db)
        code = referral_service.ensure_code_for_user(referrer.id)
        db.add(
            ReferralAttribution(
                code_id=code.id,
                referred_user_id=referred.id,
                source="test",
                ts=datetime.now(timezone.utc),
            )
        )
        db.flush()

        first_booking_id, _ = _create_completed_booking(
            db, instructor=referred, student=test_student
        )
        second_booking_id, second_completed_at = _create_completed_booking(
            db, instructor=referred, student=test_student, offset_index=2
        )

        existing_payout = InstructorReferralPayout(
            referrer_user_id=referrer.id,
            referred_instructor_id=referred.id,
            triggering_booking_id=first_booking_id,
            amount_cents=7500,
            was_founding_bonus=True,
            stripe_transfer_status="completed",
            idempotency_key=f"instructor_referral_{referred.id}",
        )
        db.add(existing_payout)
        db.flush()

        with patch("app.services.referral_service.enqueue_task"):
            result = referral_service.on_instructor_lesson_completed(
                instructor_user_id=referred.id,
                booking_id=second_booking_id,
                completed_at=second_completed_at,
            )

        assert result is None

        payouts = (
            db.query(InstructorReferralPayout)
            .filter(InstructorReferralPayout.referred_instructor_id == referred.id)
            .all()
        )
        assert len(payouts) == 1

    def test_non_referred_instructor_no_payout(
        self, db: Session, test_instructor_2: User, test_student: User
    ) -> None:
        """Instructor without attribution should not create a payout."""
        referral_service = ReferralService(db)

        booking_id, completed_at = _create_completed_booking(
            db, instructor=test_instructor_2, student=test_student
        )

        result = referral_service.on_instructor_lesson_completed(
            instructor_user_id=test_instructor_2.id,
            booking_id=booking_id,
            completed_at=completed_at,
        )

        assert result is None
        payouts = (
            db.query(InstructorReferralPayout)
            .filter(InstructorReferralPayout.referred_instructor_id == test_instructor_2.id)
            .all()
        )
        assert payouts == []

    def test_student_referrer_no_instructor_payout(
        self,
        db: Session,
        test_student: User,
        test_instructor_2: User,
    ) -> None:
        """Student referrer should not generate instructor payout."""
        referral_service = ReferralService(db)
        code = referral_service.ensure_code_for_user(test_student.id)

        db.add(
            ReferralAttribution(
                code_id=code.id,
                referred_user_id=test_instructor_2.id,
                source="test",
                ts=datetime.now(timezone.utc),
            )
        )
        db.flush()

        booking_id, completed_at = _create_completed_booking(
            db, instructor=test_instructor_2, student=test_student
        )

        result = referral_service.on_instructor_lesson_completed(
            instructor_user_id=test_instructor_2.id,
            booking_id=booking_id,
            completed_at=completed_at,
        )

        assert result is None


class TestReferralAPIIntegration:
    """Integration tests for referral API endpoints."""

    def test_stats_endpoint_returns_expected_fields(
        self, client: TestClient, auth_headers_instructor: dict
    ) -> None:
        response = client.get(
            "/api/v1/instructor-referrals/stats", headers=auth_headers_instructor
        )
        assert response.status_code == 200
        data = response.json()

        expected_fields = {
            "referral_code",
            "referral_link",
            "total_referred",
            "pending_payouts",
            "completed_payouts",
            "total_earned_cents",
            "is_founding_phase",
            "founding_spots_remaining",
            "current_bonus_cents",
        }
        assert expected_fields.issubset(data.keys())
        assert isinstance(data["total_referred"], int)
        assert isinstance(data["total_earned_cents"], int)
        assert isinstance(data["is_founding_phase"], bool)

    def test_referred_list_pagination(
        self, client: TestClient, auth_headers_instructor: dict
    ) -> None:
        response = client.get(
            "/api/v1/instructor-referrals/referred?limit=10&offset=0",
            headers=auth_headers_instructor,
        )
        assert response.status_code == 200
        data = response.json()
        assert "instructors" in data
        assert "total_count" in data
        assert isinstance(data["instructors"], list)

    def test_founding_status_public_access(self, client: TestClient) -> None:
        response = client.get("/api/v1/instructor-referrals/founding-status")
        assert response.status_code == 200
        data = response.json()
        assert "is_founding_phase" in data
        assert "total_founding_spots" in data
        assert "spots_filled" in data
        assert "spots_remaining" in data
        assert data["spots_remaining"] == data["total_founding_spots"] - data["spots_filled"]

    def test_popup_data_matches_stats(
        self, client: TestClient, auth_headers_instructor: dict
    ) -> None:
        stats_response = client.get(
            "/api/v1/instructor-referrals/stats", headers=auth_headers_instructor
        )
        popup_response = client.get(
            "/api/v1/instructor-referrals/popup-data", headers=auth_headers_instructor
        )

        assert stats_response.status_code == 200
        assert popup_response.status_code == 200

        stats = stats_response.json()
        popup = popup_response.json()

        assert stats["referral_code"] == popup["referral_code"]
        assert stats["referral_link"] == popup["referral_link"]
        assert stats["is_founding_phase"] == popup["is_founding_phase"]
        assert stats["current_bonus_cents"] == popup["bonus_amount_cents"]
