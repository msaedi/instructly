"""
Integration tests for Phase 3 credit reservation lifecycle.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.booking_lock import BookingLock
from app.models.instructor import InstructorProfile
from app.models.payment import PlatformCredit, StripeConnectedAccount
from app.models.service_catalog import InstructorService
from app.repositories.payment_repository import PaymentRepository
from app.services.booking_service import BookingService
from app.services.credit_service import CreditService
from app.tasks.payment_tasks import _process_capture_for_booking

try:  # pragma: no cover - allow execution from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch: pytest.MonkeyPatch):
    yield


def _get_service(db: Session, instructor: Any) -> tuple[InstructorProfile, InstructorService]:
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).first()
    if not profile:
        raise RuntimeError("Instructor profile not found")
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active.is_(True),
        )
        .first()
    )
    if not service:
        raise RuntimeError("Instructor service not found")
    return profile, service


def _safe_start_window(hours_from_now: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start_dt = (now + timedelta(hours=hours_from_now)).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=1)
    if end_dt.date() != start_dt.date():
        start_dt = (start_dt - timedelta(hours=2)).replace(
            minute=0, second=0, microsecond=0
        )
        end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt


def _create_booking(
    db: Session,
    *,
    student_id: str,
    instructor_id: str,
    service: InstructorService,
    hours_from_now: int,
    payment_status: str = "authorized",
    payment_intent_id: str = "pi_test",
) -> Booking:
    start_dt, end_dt = _safe_start_window(hours_from_now)
    hourly_rate = float(service.hourly_rate or 100.0)
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=service.id,
        booking_date=start_dt.date(),
        start_time=start_dt.time(),
        end_time=end_dt.time(),
        service_name="Test Service",
        hourly_rate=hourly_rate,
        total_price=hourly_rate,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test",
        location_type="neutral_location",
    )
    booking.payment_intent_id = payment_intent_id
    booking.payment_status = payment_status
    db.flush()
    return booking


def _create_credit(
    db: Session,
    *,
    user_id: str,
    amount_cents: int,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    source_type: str = "promo",
) -> PlatformCredit:
    payment_repo = PaymentRepository(db)
    credit = payment_repo.create_platform_credit(
        user_id=user_id,
        amount_cents=amount_cents,
        reason=source_type,
        source_type=source_type,
        expires_at=expires_at,
    )
    if created_at is not None:
        credit.created_at = created_at
    db.flush()
    return credit


def _ensure_connected_account(db: Session, instructor_profile_id: str) -> StripeConnectedAccount:
    account = (
        db.query(StripeConnectedAccount)
        .filter(StripeConnectedAccount.instructor_profile_id == instructor_profile_id)
        .first()
    )
    if account:
        return account
    account = StripeConnectedAccount(
        id=str(ulid.ULID()),
        instructor_profile_id=instructor_profile_id,
        stripe_account_id=f"acct_{ulid.ULID()}",
        onboarding_completed=True,
    )
    db.add(account)
    db.flush()
    return account


class TestCreditReservation:
    def test_reserve_credits_fifo(self, db: Session, test_student, test_instructor):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=30,
        )

        now = datetime.now(timezone.utc)
        credit_old = _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=5000,
            created_at=now - timedelta(days=10),
            expires_at=now + timedelta(days=90),
        )
        credit_new = _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=3000,
            created_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=90),
        )

        credit_service = CreditService(db)
        reserved_total = credit_service.reserve_credits_for_booking(
            user_id=test_student.id,
            booking_id=booking.id,
            max_amount_cents=6000,
        )
        assert reserved_total == 6000

        db.refresh(credit_old)
        db.refresh(credit_new)
        assert credit_old.status == "reserved"
        assert credit_old.reserved_amount_cents == 5000
        assert credit_new.status == "reserved"
        assert credit_new.reserved_amount_cents == 1000

        remainder = (
            db.query(PlatformCredit)
            .filter(PlatformCredit.reason == f"Remainder of {credit_new.id}")
            .first()
        )
        assert remainder is not None
        assert remainder.status == "available"
        assert remainder.amount_cents == 2000

    def test_reserve_up_to_lesson_price(self, db: Session, test_student, test_instructor):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=30,
        )

        now = datetime.now(timezone.utc)
        credit = _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=20000,
            created_at=now - timedelta(days=2),
            expires_at=now + timedelta(days=365),
        )

        credit_service = CreditService(db)
        reserved_total = credit_service.reserve_credits_for_booking(
            user_id=test_student.id,
            booking_id=booking.id,
            max_amount_cents=10000,
        )
        assert reserved_total == 10000

        db.refresh(credit)
        assert credit.status == "reserved"
        assert credit.reserved_amount_cents == 10000

        remainder = (
            db.query(PlatformCredit)
            .filter(PlatformCredit.reason == f"Remainder of {credit.id}")
            .first()
        )
        assert remainder is not None
        assert remainder.amount_cents == 10000

    def test_card_charge_credits_never_cover_fee(self, db: Session):
        credit_service = CreditService(db)
        assert (
            credit_service.get_card_charge_amount(
                lesson_price_cents=12000,
                student_fee_cents=1440,
                reserved_credits_cents=6000,
            )
            == 7440
        )
        assert (
            credit_service.get_card_charge_amount(
                lesson_price_cents=12000,
                student_fee_cents=1440,
                reserved_credits_cents=20000,
            )
            == 1440
        )


class TestCreditRelease:
    @patch("app.services.stripe_service.StripeService.cancel_payment_intent")
    def test_release_on_gt24h_cancel(
        self, mock_cancel, db: Session, test_student, test_instructor
    ):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=30,
        )

        now = datetime.now(timezone.utc)
        credit = _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=6000,
            expires_at=now + timedelta(days=45),
        )

        credit_service = CreditService(db)
        reserved = credit_service.reserve_credits_for_booking(
            user_id=test_student.id,
            booking_id=booking.id,
            max_amount_cents=6000,
        )
        booking.credits_reserved_cents = reserved
        db.flush()

        booking_service = BookingService(db)
        booking_service.cancel_booking(booking.id, user=test_student, reason="test")

        db.refresh(credit)
        assert credit.status == "available"
        assert credit.reserved_for_booking_id is None
        assert credit.reserved_amount_cents == 0
        assert credit.expires_at.astimezone(timezone.utc).date() == (
            now + timedelta(days=45)
        ).date()

    @patch("app.services.stripe_service.StripeService.cancel_payment_intent")
    def test_release_on_instructor_cancel(
        self, mock_cancel, db: Session, test_student, test_instructor
    ):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=30,
        )

        _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=4000,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        credit_service = CreditService(db)
        reserved = credit_service.reserve_credits_for_booking(
            user_id=test_student.id,
            booking_id=booking.id,
            max_amount_cents=4000,
        )
        booking.credits_reserved_cents = reserved
        db.flush()

        booking_service = BookingService(db)
        booking_service.cancel_booking(booking.id, user=test_instructor, reason="test")

        released = (
            db.query(PlatformCredit)
            .filter(PlatformCredit.reserved_for_booking_id == booking.id)
            .all()
        )
        assert released == []


class TestCreditForfeit:
    @patch("app.services.stripe_service.StripeService.reverse_transfer")
    @patch("app.services.stripe_service.StripeService.capture_payment_intent")
    def test_forfeit_on_12_24h_cancel(
        self, mock_capture, mock_reverse, db: Session, test_student, test_instructor
    ):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=18,
        )

        _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=4000,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        credit_service = CreditService(db)
        reserved = credit_service.reserve_credits_for_booking(
            user_id=test_student.id,
            booking_id=booking.id,
            max_amount_cents=4000,
        )
        booking.credits_reserved_cents = reserved
        db.flush()

        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }

        booking_service = BookingService(db)
        booking_service.cancel_booking(booking.id, user=test_student, reason="test")

        forfeited = db.query(PlatformCredit).filter(
            PlatformCredit.used_booking_id == booking.id
        )
        assert forfeited.count() == 1
        credit = forfeited.first()
        assert credit.status == "forfeited"

        issued = (
            db.query(PlatformCredit)
            .filter(
                PlatformCredit.source_booking_id == booking.id,
                PlatformCredit.source_type == "cancel_credit_12_24",
            )
            .first()
        )
        assert issued is not None
        expected_lesson_price = int(float(booking.hourly_rate) * 100)
        assert issued.amount_cents == expected_lesson_price

    @patch("app.services.stripe_service.StripeService.create_manual_transfer")
    @patch("app.services.stripe_service.StripeService.reverse_transfer")
    @patch("app.services.stripe_service.StripeService.capture_payment_intent")
    def test_forfeit_on_lt12h_cancel(
        self,
        mock_capture,
        mock_reverse,
        mock_transfer,
        db: Session,
        test_student,
        test_instructor,
    ):
        profile, service = _get_service(db, test_instructor)
        _ensure_connected_account(db, profile.id)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=6,
        )

        _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=6000,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        credit_service = CreditService(db)
        reserved = credit_service.reserve_credits_for_booking(
            user_id=test_student.id,
            booking_id=booking.id,
            max_amount_cents=6000,
        )
        booking.credits_reserved_cents = reserved
        db.flush()

        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        mock_transfer.return_value = {"transfer_id": "tr_manual"}

        booking_service = BookingService(db)
        booking_service.cancel_booking(booking.id, user=test_student, reason="test")

        forfeited = db.query(PlatformCredit).filter(
            PlatformCredit.used_booking_id == booking.id
        )
        assert forfeited.count() == 1
        credit = forfeited.first()
        assert credit.status == "forfeited"

        issued = (
            db.query(PlatformCredit)
            .filter(
                PlatformCredit.source_booking_id == booking.id,
                PlatformCredit.source_type == "cancel_credit_lt12",
            )
            .first()
        )
        assert issued is not None
        expected_lesson_price = int(float(booking.hourly_rate) * 100)
        assert issued.amount_cents == int(round(expected_lesson_price * 0.5))

    @patch("app.services.stripe_service.StripeService.capture_booking_payment_intent")
    def test_forfeit_on_lesson_completion(
        self, mock_capture, db: Session, test_student, test_instructor
    ):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=30,
        )
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_capture"
        db.flush()

        _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=4000,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        credit_service = CreditService(db)
        reserved = credit_service.reserve_credits_for_booking(
            user_id=test_student.id,
            booking_id=booking.id,
            max_amount_cents=4000,
        )
        booking.credits_reserved_cents = reserved
        db.flush()
        db.commit()

        mock_intent = MagicMock()
        mock_intent.amount_received = 13440
        mock_capture.return_value = {"payment_intent": mock_intent, "amount_received": 13440}

        _process_capture_for_booking(booking.id, "auto_completed")

        forfeited = db.query(PlatformCredit).filter(
            PlatformCredit.used_booking_id == booking.id
        )
        assert forfeited.count() == 1
        credit = forfeited.first()
        assert credit.status == "forfeited"


class TestCreditIssuance:
    def test_issue_credit_sets_expiration_and_source(
        self, db: Session, test_student, test_instructor
    ):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=30,
        )
        credit_service = CreditService(db)
        now = datetime.now(timezone.utc)
        issued = credit_service.issue_credit(
            user_id=test_student.id,
            amount_cents=6000,
            source_type="cancel_credit_lt12",
            source_booking_id=booking.id,
        )
        assert issued is not None
        assert issued.source_type == "cancel_credit_lt12"
        assert issued.source_booking_id == booking.id
        assert issued.status == "available"
        assert issued.expires_at is not None
        assert issued.expires_at.date() == (now + timedelta(days=365)).date()


class TestCreditExpiration:
    def test_reserved_credits_protected_from_expiration(
        self, db: Session, test_student, test_instructor
    ):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=30,
        )
        now = datetime.now(timezone.utc)
        expired_available = _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=1000,
            expires_at=now - timedelta(days=1),
        )
        reserved = _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=2000,
            expires_at=now - timedelta(days=1),
        )
        reserved.status = "reserved"
        reserved.reserved_amount_cents = 2000
        reserved.reserved_for_booking_id = booking.id
        reserved.reserved_at = now - timedelta(days=2)
        db.flush()

        credit_service = CreditService(db)
        expired_count = credit_service.expire_old_credits()
        assert expired_count == 1

        db.refresh(expired_available)
        db.refresh(reserved)
        assert expired_available.status == "expired"
        assert reserved.status == "reserved"


class TestCreditWithLock:
    @patch("app.services.stripe_service.StripeService.reverse_transfer")
    @patch("app.services.stripe_service.StripeService.capture_payment_intent")
    def test_lock_activation_forfeits_credits(
        self, mock_capture, mock_reverse, db: Session, test_student, test_instructor
    ):
        _, service = _get_service(db, test_instructor)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=18,
        )

        _create_credit(
            db,
            user_id=test_student.id,
            amount_cents=3000,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        credit_service = CreditService(db)
        reserved = credit_service.reserve_credits_for_booking(
            user_id=test_student.id,
            booking_id=booking.id,
            max_amount_cents=3000,
        )
        booking.credits_reserved_cents = reserved
        db.flush()

        mock_capture.return_value = {
            "transfer_id": "tr_lock",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }

        booking_service = BookingService(db)
        booking_service.activate_lock_for_reschedule(booking.id)

        forfeited = db.query(PlatformCredit).filter(
            PlatformCredit.used_booking_id == booking.id
        )
        assert forfeited.count() == 1
        credit = forfeited.first()
        assert credit.status == "forfeited"

    @patch("app.services.stripe_service.StripeService.create_manual_transfer")
    def test_lock_resolution_issues_credit(
        self,
        mock_transfer,
        db: Session,
        test_student,
        test_instructor,
        disable_price_floors,
    ):
        profile, service = _get_service(db, test_instructor)
        _ensure_connected_account(db, profile.id)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            service=service,
            hours_from_now=30,
            payment_status="locked",
        )
        db.add(BookingLock(booking_id=booking.id, locked_amount_cents=13440))
        db.flush()

        mock_transfer.return_value = {"transfer_id": "tr_lock_split"}

        booking_service = BookingService(db)
        booking_service.resolve_lock_for_booking(booking.id, "new_lesson_cancelled_lt12")

        issued = (
            db.query(PlatformCredit)
            .filter(
                PlatformCredit.source_booking_id == booking.id,
                PlatformCredit.source_type == "locked_cancel_lt12",
            )
            .first()
        )
        assert issued is not None
        expected_lesson_price = int(float(booking.hourly_rate) * 100)
        assert issued.amount_cents == int(round(expected_lesson_price * 0.5))
