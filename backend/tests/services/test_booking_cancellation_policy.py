"""
Tests for BookingService cancellation policy branches (>24h, 12–24h, <12h).
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services.booking_service import BookingService


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch: pytest.MonkeyPatch):
    yield


def _create_instructor_with_service(db: Session) -> tuple[User, InstructorProfile, InstructorService]:
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

    cat = ServiceCategory(id=str(ulid.ULID()), name="Cat", slug=f"cat-{ulid.ULID()}")
    db.add(cat)
    db.flush()

    svc_cat = ServiceCatalog(id=str(ulid.ULID()), category_id=cat.id, name="Svc", slug=f"svc-{ulid.ULID()}")
    db.add(svc_cat)
    db.flush()

    svc = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=svc_cat.id,
        hourly_rate=100.00,
        duration_options=[60],
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


def _create_booking(db: Session, student: User, instructor: User, svc: InstructorService, when: datetime) -> Booking:
    bk = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=when.date(),
        start_time=when.time(),
        end_time=(when + timedelta(hours=1)).time(),
        service_name="Svc",
        hourly_rate=100.00,
        total_price=100.00,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        payment_method_id="pm_x",
        payment_intent_id="pi_x",
    )
    db.add(bk)
    db.flush()
    return bk


def test_cancel_over_24h_releases_auth(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    # Booking 2 days out (>24h)
    when = datetime.combine(date.today() + timedelta(days=2), time(14, 0))
    bk = _create_booking(db, student, instructor, svc, when)

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.cancel_payment_intent") as mock_cancel, patch(
        "app.repositories.payment_repository.PaymentRepository.create_payment_event"
    ) as mock_event:
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "released"
    mock_cancel.assert_called_once()
    mock_event.assert_called()


def test_cancel_12_24h_capture_reverse_credit(db: Session):
    """12-24h cancellation should capture, reverse transfer, and issue credit.

    With transfer_data[amount] architecture:
    - amount_received = total charge (student paid)
    - transfer_amount = instructor payout (portion transferred)

    The reverse_transfer should only reverse the transfer_amount, NOT amount_received.
    The credit should be LESSON PRICE only (not the full amount_received or total_price).
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    # Booking ~18 hours out. Avoid crossing midnight which would wrap end_time to 00:00
    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    bk = _create_booking(db, student, instructor, svc, when)

    service = BookingService(db)

    # Mock with transfer_data[amount] architecture values:
    # - amount_received: $100 (total charge to student)
    # - transfer_amount: $88 (instructor payout after 12% platform fee)
    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ) as mock_reverse, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 10000,  # $100 total charge
            "transfer_amount": 8800,  # $88 instructor payout
        }
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "credit_issued"
    mock_capture.assert_called_once()
    mock_reverse.assert_called_once()

    # CRITICAL: Verify we reverse the transfer_amount (8800), NOT amount_received (10000)
    reverse_call_kwargs = mock_reverse.call_args.kwargs
    assert reverse_call_kwargs["amount_cents"] == 8800, (
        "Should reverse transfer_amount (instructor payout), not amount_received (total charge)"
    )

    # Verify credit was called with LESSON PRICE (10000 cents = $100/hr * 60min)
    mock_credit.assert_called_once()
    credit_call_kwargs = mock_credit.call_args.kwargs
    expected_lesson_price = 10000  # $100/hr * 60min = $100 = 10000 cents
    assert credit_call_kwargs["amount_cents"] == expected_lesson_price, (
        "Credit should be lesson price, not total_price with fees"
    )
    assert "(lesson price credit)" in credit_call_kwargs["reason"], (
        "Reason should indicate this is a lesson price credit"
    )


def test_cancel_under_12h_capture_only(db: Session):
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)
    # Booking ~3 hours out. Avoid crossing midnight which would make end_time wrap to 00:00
    # on the same booking_date and violate the DB constraint (start_time < end_time).
    when = datetime.now() + timedelta(hours=3)
    when = when.replace(minute=0, second=0, microsecond=0)
    # If adding one hour crosses the date boundary, push start into next day (01:00)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    bk = _create_booking(db, student, instructor, svc, when)

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture:
        mock_capture.return_value = {"amount_received": 10000}
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "captured"
    mock_capture.assert_called_once()


# =========================================================================
# Part 3: 12-24h Credit = Lesson Price Only (Platform Retains Fee)
# =========================================================================


def _create_booking_with_fee(
    db: Session,
    student: User,
    instructor: User,
    svc: InstructorService,
    when: datetime,
    hourly_rate: float = 120.00,
    duration_minutes: int = 60,
    student_fee_pct: float = 0.12,
) -> Booking:
    """Create a booking with an explicit student fee (total_price includes fee)."""
    lesson_price = hourly_rate * duration_minutes / 60
    student_fee = lesson_price * student_fee_pct
    total_price = lesson_price + student_fee

    bk = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=when.date(),
        start_time=when.time(),
        end_time=(when + timedelta(minutes=duration_minutes)).time(),
        service_name="Svc",
        hourly_rate=hourly_rate,
        total_price=total_price,  # Includes student fee
        duration_minutes=duration_minutes,
        status=BookingStatus.CONFIRMED,
        payment_method_id="pm_x",
        payment_intent_id="pi_x",
    )
    db.add(bk)
    db.flush()
    return bk


def test_12_24h_credit_lesson_price_only(db: Session):
    """12-24h cancellation credit should be lesson price, NOT total with fee.

    Scenario:
    - Lesson price: $120.00 (hourly_rate=$120, duration=60min)
    - Student fee: $14.40 (12%)
    - Total charged: $134.40
    - Cancel at 18h before
    - Expected credit: $120.00 (NOT $134.40)
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Booking ~18 hours out
    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    # Create booking with $120 lesson + $14.40 fee = $134.40 total
    bk = _create_booking_with_fee(
        db, student, instructor, svc, when,
        hourly_rate=120.00,
        duration_minutes=60,
        student_fee_pct=0.12,
    )

    # Verify total_price includes fee
    assert float(bk.total_price) == 134.40, "total_price should include student fee"

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, \
         patch("app.services.stripe_service.StripeService.reverse_transfer"), \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit:
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 13440,  # $134.40 total
            "transfer_amount": 10560,  # $105.60 instructor payout
        }
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "credit_issued"

    # CRITICAL: Credit should be LESSON PRICE ($120 = 12000 cents), NOT total ($134.40)
    mock_credit.assert_called_once()
    credit_kwargs = mock_credit.call_args.kwargs
    expected_lesson_price_cents = 12000  # $120 * 100
    assert credit_kwargs["amount_cents"] == expected_lesson_price_cents, (
        f"Credit should be lesson price (12000 cents = $120), "
        f"got {credit_kwargs['amount_cents']} cents"
    )


def test_platform_retains_fee_on_12_24h_cancel(db: Session):
    """Platform should retain booking protection fee on 12-24h cancellation.

    This verifies that the credit is LESS than total_price by exactly the fee amount.
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    # $120 lesson + $14.40 fee (12%) = $134.40 total
    bk = _create_booking_with_fee(
        db, student, instructor, svc, when,
        hourly_rate=120.00,
        duration_minutes=60,
        student_fee_pct=0.12,
    )

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, \
         patch("app.services.stripe_service.StripeService.reverse_transfer"), \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit:
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 13440,
            "transfer_amount": 10560,
        }
        service.cancel_booking(bk.id, user=student, reason="test")

    credit_kwargs = mock_credit.call_args.kwargs
    credit_amount = credit_kwargs["amount_cents"]

    total_charged_cents = int(bk.total_price * 100)  # 13440
    lesson_price_cents = int(float(bk.hourly_rate) * bk.duration_minutes * 100 / 60)  # 12000
    fee_retained_cents = total_charged_cents - lesson_price_cents  # 1440

    assert credit_amount == lesson_price_cents, (
        f"Credit should be lesson price only: {lesson_price_cents} cents"
    )
    assert total_charged_cents - credit_amount == fee_retained_cents, (
        f"Platform should retain fee: {fee_retained_cents} cents ($14.40)"
    )


@pytest.mark.parametrize(
    "hourly_rate,duration_minutes,expected_credit_cents",
    [
        (100.00, 60, 10000),   # $100/hr * 60min = $100 = 10000 cents
        (120.00, 60, 12000),   # $120/hr * 60min = $120 = 12000 cents
        (80.00, 90, 12000),    # $80/hr * 90min = $120 = 12000 cents
        (150.00, 30, 7500),    # $150/hr * 30min = $75 = 7500 cents
        (200.00, 45, 15000),   # $200/hr * 45min = $150 = 15000 cents
    ],
)
def test_credit_amount_matches_lesson_price(
    db: Session,
    hourly_rate: float,
    duration_minutes: int,
    expected_credit_cents: int,
):
    """Credit should be calculated from hourly_rate * duration, not from total_price."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    # Ensure end_time doesn't wrap to next day
    if (when + timedelta(minutes=duration_minutes)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    bk = _create_booking_with_fee(
        db, student, instructor, svc, when,
        hourly_rate=hourly_rate,
        duration_minutes=duration_minutes,
        student_fee_pct=0.12,
    )

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, \
         patch("app.services.stripe_service.StripeService.reverse_transfer"), \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit:
        # Total includes 12% fee
        total_cents = int(hourly_rate * duration_minutes / 60 * 1.12 * 100)
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": total_cents,
            "transfer_amount": int(total_cents * 0.88),
        }
        service.cancel_booking(bk.id, user=student, reason="test")

    credit_kwargs = mock_credit.call_args.kwargs
    assert credit_kwargs["amount_cents"] == expected_credit_cents, (
        f"Expected credit {expected_credit_cents} cents for "
        f"${hourly_rate}/hr x {duration_minutes}min"
    )
