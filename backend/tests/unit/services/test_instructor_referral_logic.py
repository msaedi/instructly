"""Tests for instructor referral business logic."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from tests.fixtures.unique_test_data import unique_data

from app.core.enums import RoleName
from app.models.booking import BookingStatus
from app.repositories.booking_repository import BookingRepository
from app.repositories.referral_repository import ReferralRewardRepository
from app.services.booking_service import BookingService
from app.services.referral_service import ReferralService

try:  # pragma: no cover - allow repo root or backend/ test execution
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


@pytest.fixture
def referral_service(db):
    service = ReferralService(db)
    service.booking_repo = Mock()
    service.instructor_profile_repo = Mock()
    service.referral_attribution_repo = Mock()
    service.referral_code_repo = Mock()
    service.referral_reward_repo = Mock()
    service.config_service = Mock()
    service._get_config = Mock(
        return_value={
            "enabled": True,
            "instructor_founding_bonus_cents": 7500,
            "instructor_standard_bonus_cents": 5000,
        }
    )
    service.config_service.get_pricing_config.return_value = (
        {"founding_instructor_cap": 100},
        None,
    )
    return service


class TestOnInstructorLessonCompleted:
    """Tests for the on_instructor_lesson_completed trigger."""

    def test_first_lesson_triggers_payout(self, referral_service):
        service = referral_service
        service.booking_repo.count_instructor_total_completed.return_value = 1

        attribution = Mock(code_id="code_1")
        service.referral_attribution_repo.get_by_referred_user_id.return_value = attribution
        service.referral_code_repo.get_by_id.return_value = Mock(referrer_user_id="referrer_123")

        referrer_profile = Mock(stripe_connected_account=Mock())
        service.instructor_profile_repo.get_by_user_id.return_value = referrer_profile
        service.instructor_profile_repo.count_founding_instructors.return_value = 50

        payout = Mock(id="payout_123")
        service.referral_reward_repo.create_instructor_referral_payout.return_value = payout

        result = service.on_instructor_lesson_completed(
            instructor_user_id="instructor_456",
            booking_id="booking_789",
            completed_at=datetime.now(timezone.utc),
        )

        assert result == "payout_123"
        call_kwargs = service.referral_reward_repo.create_instructor_referral_payout.call_args.kwargs
        assert call_kwargs["amount_cents"] == 7500
        assert call_kwargs["was_founding_bonus"] is True

    def test_second_lesson_does_not_trigger_payout(self, referral_service):
        service = referral_service
        service.booking_repo.count_instructor_total_completed.return_value = 2

        result = service.on_instructor_lesson_completed(
            instructor_user_id="instructor_456",
            booking_id="booking_789",
            completed_at=datetime.now(timezone.utc),
        )

        assert result is None
        service.referral_reward_repo.create_instructor_referral_payout.assert_not_called()

    def test_non_referred_instructor_no_payout(self, referral_service):
        service = referral_service
        service.booking_repo.count_instructor_total_completed.return_value = 1
        service.referral_attribution_repo.get_by_referred_user_id.return_value = None

        result = service.on_instructor_lesson_completed(
            instructor_user_id="instructor_456",
            booking_id="booking_789",
            completed_at=datetime.now(timezone.utc),
        )

        assert result is None
        service.referral_reward_repo.create_instructor_referral_payout.assert_not_called()

    def test_referrer_not_instructor_no_payout(self, referral_service):
        service = referral_service
        service.booking_repo.count_instructor_total_completed.return_value = 1
        service.referral_attribution_repo.get_by_referred_user_id.return_value = Mock(
            code_id="code_1"
        )
        service.referral_code_repo.get_by_id.return_value = Mock(referrer_user_id="referrer_123")
        service.instructor_profile_repo.get_by_user_id.return_value = None

        result = service.on_instructor_lesson_completed(
            instructor_user_id="instructor_456",
            booking_id="booking_789",
            completed_at=datetime.now(timezone.utc),
        )

        assert result is None
        service.referral_reward_repo.create_instructor_referral_payout.assert_not_called()

    def test_referrer_without_stripe_account_no_payout(self, referral_service):
        service = referral_service
        service.booking_repo.count_instructor_total_completed.return_value = 1
        service.referral_attribution_repo.get_by_referred_user_id.return_value = Mock(
            code_id="code_1"
        )
        service.referral_code_repo.get_by_id.return_value = Mock(referrer_user_id="referrer_123")
        service.instructor_profile_repo.get_by_user_id.return_value = Mock(
            stripe_connected_account=None
        )

        result = service.on_instructor_lesson_completed(
            instructor_user_id="instructor_456",
            booking_id="booking_789",
            completed_at=datetime.now(timezone.utc),
        )

        assert result is None
        service.referral_reward_repo.create_instructor_referral_payout.assert_not_called()

    def test_post_founding_pays_standard_bonus(self, referral_service):
        service = referral_service
        service.booking_repo.count_instructor_total_completed.return_value = 1
        service.referral_attribution_repo.get_by_referred_user_id.return_value = Mock(
            code_id="code_1"
        )
        service.referral_code_repo.get_by_id.return_value = Mock(referrer_user_id="referrer_123")
        service.instructor_profile_repo.get_by_user_id.return_value = Mock(
            stripe_connected_account=Mock()
        )
        service.instructor_profile_repo.count_founding_instructors.return_value = 100

        payout = Mock(id="payout_123")
        service.referral_reward_repo.create_instructor_referral_payout.return_value = payout

        result = service.on_instructor_lesson_completed(
            instructor_user_id="instructor_456",
            booking_id="booking_789",
            completed_at=datetime.now(timezone.utc),
        )

        assert result == "payout_123"
        call_kwargs = service.referral_reward_repo.create_instructor_referral_payout.call_args.kwargs
        assert call_kwargs["amount_cents"] == 5000
        assert call_kwargs["was_founding_bonus"] is False

    def test_idempotency_prevents_duplicate_payout(self, referral_service):
        service = referral_service
        service.booking_repo.count_instructor_total_completed.return_value = 1
        service.referral_attribution_repo.get_by_referred_user_id.return_value = Mock(
            code_id="code_1"
        )
        service.referral_code_repo.get_by_id.return_value = Mock(referrer_user_id="referrer_123")
        service.instructor_profile_repo.get_by_user_id.return_value = Mock(
            stripe_connected_account=Mock()
        )
        service.instructor_profile_repo.count_founding_instructors.return_value = 50
        service.referral_reward_repo.create_instructor_referral_payout.return_value = None

        result = service.on_instructor_lesson_completed(
            instructor_user_id="instructor_456",
            booking_id="booking_789",
            completed_at=datetime.now(timezone.utc),
        )

        assert result is None


class TestCountInstructorTotalCompleted:
    """Tests for the count_instructor_total_completed repository method."""

    def test_count_zero_for_new_instructor(self, db):
        repo = BookingRepository(db)
        count = repo.count_instructor_total_completed("nonexistent_instructor")
        assert count == 0

    def test_counts_only_completed_lessons(self, db, test_booking):
        repo = BookingRepository(db)
        booking = test_booking
        booking.status = BookingStatus.COMPLETED
        booking.completed_at = datetime.now(timezone.utc)
        db.flush()

        create_booking_pg_safe(
            db,
            student_id=booking.student_id,
            instructor_id=booking.instructor_id,
            instructor_service_id=booking.instructor_service_id,
            booking_date=booking.booking_date + timedelta(days=1),
            start_time=booking.start_time,
            end_time=booking.end_time,
            status=BookingStatus.CONFIRMED,
            service_name=booking.service_name,
            hourly_rate=booking.hourly_rate,
            total_price=booking.total_price,
            duration_minutes=booking.duration_minutes,
            meeting_location=booking.meeting_location,
            service_area=booking.service_area,
            cancel_duplicate=True,
        )

        create_booking_pg_safe(
            db,
            student_id=booking.student_id,
            instructor_id=booking.instructor_id,
            instructor_service_id=booking.instructor_service_id,
            booking_date=booking.booking_date + timedelta(days=2),
            start_time=booking.start_time,
            end_time=booking.end_time,
            status=BookingStatus.CANCELLED,
            service_name=booking.service_name,
            hourly_rate=booking.hourly_rate,
            total_price=booking.total_price,
            duration_minutes=booking.duration_minutes,
            meeting_location=booking.meeting_location,
            service_area=booking.service_area,
            cancel_duplicate=True,
        )

        count = repo.count_instructor_total_completed(booking.instructor_id)
        assert count == 1


class TestCreateInstructorReferralPayout:
    """Tests for create_instructor_referral_payout repository method."""

    def test_creates_payout_record(self, db, test_instructor, test_instructor_2, test_booking):
        repo = ReferralRewardRepository(db)
        payout = repo.create_instructor_referral_payout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=f"payout_{unique_data.unique_slug('key')}",
        )

        assert payout is not None
        assert payout.referrer_user_id == test_instructor.id
        assert payout.referred_instructor_id == test_instructor_2.id
        assert payout.amount_cents == 7500
        assert payout.was_founding_bonus is True

    def test_idempotency_key_returns_none(self, db, test_instructor, test_instructor_2, test_booking):
        repo = ReferralRewardRepository(db)
        idempotency_key = f"payout_{unique_data.unique_slug('key')}"

        repo.create_instructor_referral_payout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=idempotency_key,
        )

        payout = repo.create_instructor_referral_payout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=idempotency_key,
        )

        assert payout is None

    def test_duplicate_referred_instructor_returns_none(
        self, db, test_instructor, test_instructor_2, test_booking
    ):
        repo = ReferralRewardRepository(db)
        repo.create_instructor_referral_payout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=7500,
            was_founding_bonus=True,
            idempotency_key=f"payout_{unique_data.unique_slug('key')}",
        )

        payout = repo.create_instructor_referral_payout(
            referrer_user_id=test_instructor.id,
            referred_instructor_id=test_instructor_2.id,
            triggering_booking_id=test_booking.id,
            amount_cents=5000,
            was_founding_bonus=False,
            idempotency_key=f"payout_{unique_data.unique_slug('key')}",
        )

        assert payout is None


class TestBookingServiceReferralIntegration:
    """Tests for BookingService referral trigger integration."""

    def _build_service(self, db):
        repository = Mock()
        initial_booking = SimpleNamespace(
            id="booking_1",
            instructor_id="instructor_1",
            student_id="student_1",
            status=BookingStatus.CONFIRMED,
            completed_at=None,
            booking_date=date.today(),
            instructor_service=None,
        )
        completed_booking = SimpleNamespace(
            id="booking_1",
            instructor_id="instructor_1",
            student_id="student_1",
            status=BookingStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            booking_date=date.today(),
            instructor_service=None,
        )
        repository.get_booking_with_details.side_effect = [initial_booking, completed_booking]
        repository.complete_booking.return_value = completed_booking

        service = BookingService(
            db,
            notification_service=Mock(),
            system_message_service=Mock(),
            repository=repository,
        )
        service._snapshot_booking = Mock(return_value={})
        service._enqueue_booking_outbox_event = Mock()
        service._write_booking_audit = Mock()
        service._invalidate_booking_caches = Mock()
        return service, completed_booking

    def test_booking_completion_calls_referral_trigger(self, db):
        service, completed_booking = self._build_service(db)
        instructor = SimpleNamespace(
            id="instructor_1",
            roles=[SimpleNamespace(name=RoleName.INSTRUCTOR)],
        )

        with patch(
            "app.services.booking_service.StudentCreditService"
        ) as mock_credit_service, patch(
            "app.services.referral_service.ReferralService"
        ) as mock_referral_class:
            mock_credit_service.return_value.maybe_issue_milestone_credit.return_value = None
            referral_instance = mock_referral_class.return_value
            referral_instance.on_instructor_lesson_completed.return_value = "payout_123"

            result = service.complete_booking("booking_1", instructor)

        assert result == completed_booking
        referral_instance.on_instructor_lesson_completed.assert_called_once_with(
            instructor_user_id="instructor_1",
            booking_id="booking_1",
            completed_at=completed_booking.completed_at,
        )

    def test_referral_failure_does_not_fail_completion(self, db):
        service, completed_booking = self._build_service(db)
        instructor = SimpleNamespace(
            id="instructor_1",
            roles=[SimpleNamespace(name=RoleName.INSTRUCTOR)],
        )

        with patch(
            "app.services.booking_service.StudentCreditService"
        ) as mock_credit_service, patch(
            "app.services.referral_service.ReferralService"
        ) as mock_referral_class:
            mock_credit_service.return_value.maybe_issue_milestone_credit.return_value = None
            referral_instance = mock_referral_class.return_value
            referral_instance.on_instructor_lesson_completed.side_effect = RuntimeError("boom")

            result = service.complete_booking("booking_1", instructor)

        assert result == completed_booking
