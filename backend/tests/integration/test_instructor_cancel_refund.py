"""
Integration tests for instructor cancellation refunds (policy v2.1.1).
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.booking_payment import BookingPayment
from app.models.instructor import InstructorProfile
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
        hourly_rate=100.00,
        duration_options=[60],
        offers_travel=True,
        offers_at_location=True,
        offers_online=True,
        is_active=True,
    )
    db.add(svc)
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
        hourly_rate=100.00,
        total_price=100.00,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
    )
    db.add(bk)
    db.flush()
    bp = BookingPayment(id=str(ulid.ULID()), booking_id=bk.id, payment_method_id="pm_x", payment_intent_id="pi_x")
    db.add(bp)
    db.flush()
    return bk


def test_refund_when_captured(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.combine(date.today() + timedelta(days=1), time(14, 0))
    booking = _create_booking(db, student, instructor, svc, when)
    from app.models.booking_payment import BookingPayment as BP
    bp = db.query(BP).filter(BP.booking_id == booking.id).first()
    if bp:
        bp.payment_status = "settled"
    db.commit()

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.refund_payment") as mock_refund, patch(
        "app.services.stripe_service.StripeService.cancel_payment_intent"
    ) as mock_cancel, patch(
        "app.services.booking_service.StudentCreditService"
    ) as mock_credit_service:
        mock_refund.return_value = {"refund_id": "re_test", "amount_refunded": 10000}
        result = service.cancel_booking(booking.id, user=instructor, reason="test")

    assert result.payment_detail.payment_status == "settled"
    assert result.payment_detail.settlement_outcome == "instructor_cancel_full_refund"
    assert result.payment_detail.settlement_outcome == "instructor_cancel_full_refund"
    assert result.student_credit_amount == 0
    assert result.payment_detail.instructor_payout_amount == 0
    assert result.refunded_to_card_amount == 10000
    mock_refund.assert_called_once()
    refund_kwargs = mock_refund.call_args.kwargs
    assert refund_kwargs["reverse_transfer"] is True
    assert refund_kwargs["refund_application_fee"] is True
    assert "amount_cents" not in refund_kwargs  # Full refund including SF
    mock_cancel.assert_not_called()
    mock_credit_service.return_value.process_refund_hooks.assert_called_once()


def test_release_auth_when_not_captured(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    when = datetime.combine(date.today() + timedelta(days=2), time(14, 0))
    booking = _create_booking(db, student, instructor, svc, when)
    bp2 = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    if bp2:
        bp2.payment_status = "authorized"
    db.commit()

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.refund_payment") as mock_refund, patch(
        "app.services.stripe_service.StripeService.cancel_payment_intent"
    ) as mock_cancel, patch(
        "app.services.booking_service.StudentCreditService"
    ) as mock_credit_service:
        result = service.cancel_booking(booking.id, user=instructor, reason="test")

    assert result.payment_detail.payment_status == "settled"
    assert result.payment_detail.settlement_outcome == "instructor_cancel_full_refund"
    assert result.student_credit_amount == 0
    assert result.payment_detail.instructor_payout_amount == 0
    assert result.refunded_to_card_amount == 0
    mock_cancel.assert_called_once()
    mock_refund.assert_not_called()
    mock_credit_service.return_value.process_refund_hooks.assert_called_once()
