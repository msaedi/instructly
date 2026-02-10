"""
Integration tests for <12h cancellation 50/50 split (policy v2.1.1).
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import StripeConnectedAccount
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.models.user import User
from app.services.booking_service import BookingService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch: pytest.MonkeyPatch):
    yield


def _create_instructor_with_service(
    db: Session,
) -> tuple[User, InstructorProfile, InstructorService]:
    instructor = User(
        id=str(ulid.ULID()),
        email=f"inst_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="Inst",
        last_name="Ructor",
        is_active=True,
        zip_code="10001",
    )
    db.add(instructor)
    db.flush()

    profile = InstructorProfile(
        id=str(ulid.ULID()),
        user_id=instructor.id,
        bio="bio",
        years_experience=3,
    )
    db.add(profile)
    db.flush()

    cat = ServiceCategory(id=str(ulid.ULID()), name="Cat")
    db.add(cat)
    db.flush()

    sub = ServiceSubcategory(id=str(ulid.ULID()), name="General", category_id=cat.id, display_order=1)
    db.add(sub)
    db.flush()

    svc_cat = ServiceCatalog(id=str(ulid.ULID()), subcategory_id=sub.id, name="Svc", slug=f"svc-{ulid.ULID()}")
    db.add(svc_cat)
    db.flush()

    svc = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=svc_cat.id,
        hourly_rate=120.00,
        duration_options=[60],
        offers_travel=True,
        offers_at_location=True,
        offers_online=True,
        is_active=True,
    )
    db.add(svc)
    db.flush()

    connected = StripeConnectedAccount(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        stripe_account_id="acct_test",
        onboarding_completed=True,
    )
    db.add(connected)
    db.flush()

    return instructor, profile, svc


def _create_student(db: Session) -> User:
    student = User(
        id=str(ulid.ULID()),
        email=f"stud_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="Stu",
        last_name="Dent",
        is_active=True,
        zip_code="10001",
    )
    db.add(student)
    db.flush()
    return student


def _create_booking(
    db: Session, student: User, instructor: User, svc: InstructorService, when: datetime
) -> Booking:
    booking_date = when.date()
    start_time = when.time()
    end_time = (when + timedelta(hours=1)).time()
    bk = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        **booking_timezone_fields(booking_date, start_time, end_time),
        service_name="Svc",
        hourly_rate=120.00,
        total_price=120.00,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        payment_method_id="pm_x",
        payment_intent_id="pi_x",
        payment_status="authorized",
    )
    db.add(bk)
    db.flush()
    return bk


@pytest.fixture
def lt12_booking(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.now() + timedelta(hours=3)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    booking = _create_booking(db, student, instructor, svc, when)
    return booking, student


def test_capture_and_reverse_transfer(lt12_booking, db: Session):
    booking, student = lt12_booking
    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ) as mock_reverse, patch(
        "app.services.stripe_service.StripeService.create_manual_transfer"
    ) as mock_transfer, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ):
        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        service.cancel_booking(booking.id, user=student, reason="test")

    mock_reverse.assert_called_once()
    reverse_kwargs = mock_reverse.call_args.kwargs
    assert reverse_kwargs["amount_cents"] == 10560


def test_instructor_receives_50_percent_payout(lt12_booking, db: Session):
    booking, student = lt12_booking
    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ), patch(
        "app.services.stripe_service.StripeService.create_manual_transfer"
    ) as mock_transfer, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ):
        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        service.cancel_booking(booking.id, user=student, reason="test")

    transfer_kwargs = mock_transfer.call_args.kwargs
    assert transfer_kwargs["amount_cents"] == 5280


def test_student_receives_50_percent_credit(lt12_booking, db: Session):
    booking, student = lt12_booking
    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ), patch(
        "app.services.stripe_service.StripeService.create_manual_transfer"
    ) as mock_transfer, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        service.cancel_booking(booking.id, user=student, reason="test")

    credit_kwargs = mock_credit.call_args.kwargs
    assert credit_kwargs["amount_cents"] == 6000


def test_student_keeps_no_sf_refund(lt12_booking, db: Session):
    booking, student = lt12_booking
    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ), patch(
        "app.services.stripe_service.StripeService.create_manual_transfer"
    ) as mock_transfer, patch(
        "app.services.stripe_service.StripeService.refund_payment"
    ) as mock_refund, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ):
        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        service.cancel_booking(booking.id, user=student, reason="test")

    mock_refund.assert_not_called()


def test_payment_events_logged(lt12_booking, db: Session):
    booking, student = lt12_booking
    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ), patch(
        "app.services.stripe_service.StripeService.create_manual_transfer"
    ) as mock_transfer, patch(
        "app.repositories.payment_repository.PaymentRepository.create_payment_event"
    ) as mock_events, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ):
        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        service.cancel_booking(booking.id, user=student, reason="test")

    event_types = [kwargs.get("event_type") for _, kwargs in mock_events.call_args_list]
    assert "captured_last_minute_cancel" in event_types
    assert "transfer_reversed_last_minute_cancel" in event_types
    assert "payout_created_last_minute_cancel" in event_types
    assert "credit_created_last_minute_cancel" in event_types


def test_lt12_cancel_sets_settlement_fields(lt12_booking, db: Session):
    booking, student = lt12_booking
    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ), patch(
        "app.services.stripe_service.StripeService.create_manual_transfer"
    ) as mock_transfer, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ):
        mock_capture.return_value = {
            "transfer_id": "tr_test",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        result = service.cancel_booking(booking.id, user=student, reason="test")

    assert result.settlement_outcome == "student_cancel_lt12_split_50_50"
    assert result.student_credit_amount == 6000
    assert result.instructor_payout_amount == 5280
    assert result.refunded_to_card_amount == 0
