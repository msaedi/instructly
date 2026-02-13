"""
Tests for BookingService cancellation policy branches (>24h, 12–24h, <12h).
"""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.core.exceptions import BusinessRuleException
from app.models.booking import Booking, BookingStatus
from app.models.booking_reschedule import BookingReschedule
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


def _create_booking(db: Session, student: User, instructor: User, svc: InstructorService, when: datetime) -> Booking:
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
        **booking_timezone_fields(
            booking_date,
            start_time,
            end_time,
            instructor_timezone="UTC",
            student_timezone="UTC",
        ),
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


def _upsert_reschedule(db: Session, booking_id: str, **fields: object) -> BookingReschedule:
    row = db.query(BookingReschedule).filter(BookingReschedule.booking_id == booking_id).one_or_none()
    if row is None:
        row = BookingReschedule(booking_id=booking_id)
        db.add(row)
    for key, value in fields.items():
        setattr(row, key, value)
    db.flush()
    return row


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
    assert result.payment_status == "settled"
    assert result.settlement_outcome == "student_cancel_gt24_no_charge"
    assert result.student_credit_amount == 0
    assert result.instructor_payout_amount == 0
    assert result.refunded_to_card_amount == 0
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

    expected_lesson_price = 10000  # $100/hr * 60min = $100 = 10000 cents

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "settled"
    assert result.settlement_outcome == "student_cancel_12_24_full_credit"
    assert result.student_credit_amount == expected_lesson_price
    assert result.instructor_payout_amount == 0
    assert result.refunded_to_card_amount == 0
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
    assert credit_call_kwargs["amount_cents"] == expected_lesson_price, (
        "Credit should be lesson price, not total_price with fees"
    )
    assert "(lesson price credit)" in credit_call_kwargs["reason"], (
        "Reason should indicate this is a lesson price credit"
    )


def test_cancel_under_12h_split_credit_and_payout(db: Session):
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

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ) as mock_reverse, patch(
        "app.services.stripe_service.StripeService.create_manual_transfer"
    ) as mock_transfer, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit, patch(
        "app.repositories.payment_repository.PaymentRepository.get_connected_account_by_instructor_id",
        return_value=SimpleNamespace(stripe_account_id="acct_test"),
    ):
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 10000,
            "transfer_amount": 8800,
        }
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status in {"settled", "manual_review"}
    mock_capture.assert_called_once()
    mock_reverse.assert_called_once()
    mock_transfer.assert_called_once()
    mock_credit.assert_called_once()


def test_12_24h_cancel_no_credit_on_failed_capture(db: Session):
    """Credit should not be issued if capture fails."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    bk = _create_booking(db, student, instructor, svc, when)
    bk.payment_status = "authorized"

    service = BookingService(db)

    with patch(
        "app.services.stripe_service.StripeService.capture_payment_intent",
        side_effect=Exception("Card declined"),
    ), patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.payment_status == "payment_method_required"
    mock_credit.assert_not_called()


def test_instructor_cancel_under_24h_full_refund(db: Session):
    """Instructor cancellation should always release auth and refund student."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    when = datetime.now() + timedelta(hours=6)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    bk = _create_booking(db, student, instructor, svc, when)
    bk.payment_status = "authorized"

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.cancel_payment_intent") as mock_cancel, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        result = service.cancel_booking(bk.id, user=instructor, reason="test")

    assert result.payment_status == "settled"
    mock_cancel.assert_called_once()
    mock_credit.assert_not_called()


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

    booking_date = when.date()
    start_time = when.time()
    end_time = (when + timedelta(minutes=duration_minutes)).time()
    bk = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        **booking_timezone_fields(
            booking_date,
            start_time,
            end_time,
            instructor_timezone="UTC",
            student_timezone="UTC",
        ),
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
    assert result.payment_status == "settled"

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


def test_12_24h_cancel_full_credit_when_credits_reserved(db: Session):
    """Cancellation credit is full lesson price even when credits were reserved."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    bk = _create_booking_with_fee(
        db, student, instructor, svc, when,
        hourly_rate=100.00,
        duration_minutes=60,
        student_fee_pct=0.12,
    )
    bk.payment_status = "authorized"

    service = BookingService(db)

    with patch(
        "app.repositories.payment_repository.PaymentRepository.get_credits_used_by_booking",
        return_value=[("credit_1", 3000)],
    ), patch(
        "app.services.stripe_service.StripeService.capture_payment_intent"
    ) as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ), patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit, patch(
        "app.services.booking_service.StudentCreditService.process_refund_hooks"
    ) as mock_refund_hooks:
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 11200,
            "transfer_amount": 8800,
        }
        service.cancel_booking(bk.id, user=student, reason="test")

    credit_amounts = [call.kwargs.get("amount_cents") for call in mock_credit.call_args_list]
    expected_lesson_price = int(float(bk.hourly_rate) * 100)
    assert expected_lesson_price in credit_amounts, (
        "Credit should be full lesson price (reserved credits are forfeited)"
    )
    mock_refund_hooks.assert_not_called()


def test_12_24h_cancel_skips_duplicate_credit(db: Session):
    """Cancellation should not issue credit twice if one already exists."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    bk = _create_booking_with_fee(
        db, student, instructor, svc, when,
        hourly_rate=100.00,
        duration_minutes=60,
        student_fee_pct=0.12,
    )
    bk.payment_status = "authorized"

    existing_credit = SimpleNamespace(
        reason="Cancellation 12-24 hours before lesson (lesson price credit)"
    )
    service = BookingService(db)

    with patch(
        "app.services.booking_service.TimezoneService.hours_until",
        return_value=18.0,
    ), patch(
        "app.repositories.payment_repository.PaymentRepository.get_credits_issued_for_source",
        return_value=[existing_credit],
    ), patch(
        "app.services.stripe_service.StripeService.capture_payment_intent"
    ) as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ), patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 11200,
            "transfer_amount": 8800,
        }
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.payment_status == "settled"
    mock_credit.assert_not_called()


def test_cancel_exactly_12h_gets_credit(db: Session):
    """Cancellation exactly 12h before should receive credit (12-24h window)."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    lesson_time = (fixed_now + timedelta(hours=12)).replace(tzinfo=None)
    bk = _create_booking(db, student, instructor, svc, lesson_time)
    bk.payment_status = "authorized"

    service = BookingService(db)

    with patch(
        "app.services.booking_service.TimezoneService.hours_until",
        return_value=12.0,
    ), patch(
        "app.services.stripe_service.StripeService.capture_payment_intent"
    ) as mock_capture, patch(
        "app.services.stripe_service.StripeService.reverse_transfer"
    ), patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 10000,
            "transfer_amount": 8800,
        }
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.payment_status == "settled"
    mock_credit.assert_called_once()


def test_cancel_exactly_24h_gets_full_refund(db: Session):
    """Cancellation exactly 24h before should receive full refund (release auth)."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    lesson_time = (fixed_now + timedelta(hours=24)).replace(tzinfo=None)
    bk = _create_booking(db, student, instructor, svc, lesson_time)
    bk.payment_status = "authorized"

    service = BookingService(db)

    with patch(
        "app.services.booking_service.TimezoneService.hours_until",
        return_value=24.0,
    ), patch(
        "app.services.stripe_service.StripeService.cancel_payment_intent"
    ) as mock_cancel, patch(
        "app.repositories.payment_repository.PaymentRepository.create_platform_credit"
    ) as mock_credit:
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.payment_status == "settled"
    mock_cancel.assert_called_once()
    mock_credit.assert_not_called()


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


# =========================================================================
# Part 4b: Fair Reschedule Loophole Tests
# =========================================================================


def _create_rescheduled_booking(
    db: Session,
    student: User,
    instructor: User,
    svc: InstructorService,
    when: datetime,
    original_booking_id: str,
    original_lesson_datetime: Optional[datetime] = None,  # For fair policy
    hourly_rate: float = 100.00,
    duration_minutes: int = 60,
) -> Booking:
    """Create a booking that was rescheduled from another booking.

    Args:
        original_lesson_datetime: The datetime of the original lesson. If provided,
            this is used for the fair cancellation policy to determine if the
            reschedule was a "gaming" attempt (<24h from original) or legitimate (>24h).
    """
    booking_date = when.date()
    start_time = when.time()
    end_time = (when + timedelta(minutes=duration_minutes)).time()
    bk = Booking(
        id=str(ulid.ULID()),
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=svc.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        **booking_timezone_fields(
            booking_date,
            start_time,
            end_time,
            instructor_timezone="UTC",
            student_timezone="UTC",
        ),
        service_name="Svc",
        hourly_rate=hourly_rate,
        total_price=hourly_rate * duration_minutes / 60,
        duration_minutes=duration_minutes,
        status=BookingStatus.CONFIRMED,
        payment_method_id="pm_x",
        payment_intent_id="pi_x",
        rescheduled_from_booking_id=original_booking_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(bk)
    db.flush()
    _upsert_reschedule(
        db,
        bk.id,
        original_lesson_datetime=original_lesson_datetime,
    )
    return bk


def test_rescheduled_booking_over_24h_gets_credit_not_refund(db: Session):
    """GAMING SCENARIO: Rescheduled booking cancelled >24h before should get credit, NOT card refund.

    This tests Part 4b Fair Policy with a GAMING reschedule:
    - Original lesson was ~18h away (in 12-24h penalty window)
    - Student reschedules to 5 days out to escape penalty
    - With loophole closed: credit-only, NOT card refund
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Create an actual original booking (FK requires it to exist)
    # Original was in 12-24h window (~18h away) = GAMING scenario
    original_time = datetime.now(timezone.utc) + timedelta(hours=18)
    original_time = original_time.replace(minute=0, second=0, microsecond=0)
    if (original_time + timedelta(hours=1)).date() != original_time.date():
        original_time = (original_time + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    original_booking = _create_booking(db, student, instructor, svc, original_time)
    original_booking.status = BookingStatus.CANCELLED  # Simulate cancelled via reschedule
    db.flush()

    # New booking is 5 days out (>24h)
    when = datetime.combine(date.today() + timedelta(days=5), time(14, 0))
    # Set original_lesson_datetime to mark this as a GAMING reschedule
    # (original was <24h away when rescheduled)
    bk = _create_rescheduled_booking(
        db, student, instructor, svc, when, original_booking.id,
        original_lesson_datetime=original_time,  # Gaming: original was ~18h away
    )
    bk.payment_status = "authorized"
    db.flush()

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, \
         patch("app.services.stripe_service.StripeService.reverse_transfer") as mock_reverse, \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit, \
         patch("app.repositories.payment_repository.PaymentRepository.create_payment_event"):
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 10000,
            "transfer_amount": 8800,
        }
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    # CRITICAL: Settlement outcome should reflect credit, not release.
    assert result.payment_status == "settled", (
        "Rescheduled booking >24h should get credit, not full release"
    )

    # Verify PI was captured and transfer reversed (to retain platform fee)
    mock_capture.assert_called_once()
    mock_reverse.assert_called_once()

    # Verify credit was issued for lesson price
    mock_credit.assert_called_once()
    credit_kwargs = mock_credit.call_args.kwargs
    expected_lesson_price = 10000  # $100/hr * 60min = $100 = 10000 cents
    assert credit_kwargs["amount_cents"] == expected_lesson_price
    assert "Rescheduled" in credit_kwargs["reason"]


def test_rescheduled_booking_12_24h_gets_credit(db: Session):
    """Rescheduled booking cancelled 12-24h before should get credit (same as regular)."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Create an actual original booking (FK requires it to exist)
    original_time = datetime.combine(date.today() + timedelta(days=5), time(14, 0))
    original_booking = _create_booking(db, student, instructor, svc, original_time)
    original_booking.status = BookingStatus.CANCELLED  # Simulate cancelled via reschedule
    db.flush()

    # Booking ~18 hours out (12-24h window)
    when = datetime.now() + timedelta(hours=18)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    bk = _create_rescheduled_booking(
        db, student, instructor, svc, when, original_booking.id
    )

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, \
         patch("app.services.stripe_service.StripeService.reverse_transfer"), \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit:
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 10000,
            "transfer_amount": 8800,
        }
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == "settled"
    mock_credit.assert_called_once()


def test_rescheduled_booking_under_12h_split_credit_and_payout(db: Session):
    """Rescheduled booking cancelled <12h before should follow 50/50 split."""
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Create an actual original booking (FK requires it to exist)
    original_time = datetime.combine(date.today() + timedelta(days=5), time(14, 0))
    original_booking = _create_booking(db, student, instructor, svc, original_time)
    original_booking.status = BookingStatus.CANCELLED  # Simulate cancelled via reschedule
    db.flush()

    # Booking ~3 hours out (<12h)
    when = datetime.now() + timedelta(hours=3)
    when = when.replace(minute=0, second=0, microsecond=0)
    if (when + timedelta(hours=1)).date() != when.date():
        when = (when + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    bk = _create_rescheduled_booking(
        db, student, instructor, svc, when, original_booking.id
    )

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, \
         patch("app.services.stripe_service.StripeService.reverse_transfer"), \
         patch("app.services.stripe_service.StripeService.create_manual_transfer") as mock_transfer, \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit, \
         patch(
             "app.repositories.payment_repository.PaymentRepository.get_connected_account_by_instructor_id",
             return_value=SimpleNamespace(stripe_account_id="acct_test"),
         ):
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 10000,
            "transfer_amount": 8800,
        }
        mock_transfer.return_value = {"transfer_id": "tr_payout"}
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status in {"settled", "manual_review"}
    mock_capture.assert_called_once()
    mock_transfer.assert_called_once()
    mock_credit.assert_called_once()


def test_regular_booking_over_24h_gets_card_refund(db: Session):
    """Regular (non-rescheduled) booking >24h before should still get full release.

    This ensures the existing behavior is preserved for regular bookings.
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Regular booking (no rescheduled_from_booking_id) 5 days out
    when = datetime.combine(date.today() + timedelta(days=5), time(14, 0))
    bk = _create_booking(db, student, instructor, svc, when)

    # Verify it's NOT a rescheduled booking
    assert bk.rescheduled_from_booking_id is None

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.cancel_payment_intent") as mock_cancel, \
         patch("app.repositories.payment_repository.PaymentRepository.create_payment_event"):
        result = service.cancel_booking(bk.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED
    # Regular booking >24h should settle with student_cancel_gt24_no_charge
    assert result.payment_status == "settled", (
        "Regular booking >24h should get full release, not credit"
    )
    mock_cancel.assert_called_once()


def test_reschedule_loophole_closed(db: Session):
    """GAMING SCENARIO: End-to-end test proving the loophole is closed.

    Part 4b Fair Policy - This is the core loophole test:
    1. Student has a booking tomorrow 2pm (20 hours away, in 12-24h window)
    2. If cancelled now: would get credit-only (12-24h policy)
    3. Student reschedules to next week (7+ days away)
    4. If the loophole existed: student cancels and gets full refund
    5. With loophole fixed: student cancels and still gets credit-only

    The key: we track original_lesson_datetime to detect this gaming attempt.
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Step 1: Create original booking 20 hours out (in 12-24h window) = GAMING scenario
    original_time = datetime.now(timezone.utc) + timedelta(hours=20)
    original_time = original_time.replace(minute=0, second=0, microsecond=0)
    if (original_time + timedelta(hours=1)).date() != original_time.date():
        original_time = (original_time + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    original_booking = _create_booking(db, student, instructor, svc, original_time)
    original_booking.status = BookingStatus.CANCELLED  # Simulate it was cancelled via reschedule
    db.flush()

    # Step 2: "Reschedule" creates new booking 7 days out (>24h)
    new_time = datetime.combine(date.today() + timedelta(days=7), time(14, 0))
    # CRITICAL: Set original_lesson_datetime to flag this as a GAMING reschedule
    rescheduled_booking = _create_rescheduled_booking(
        db, student, instructor, svc, new_time, original_booking.id,
        original_lesson_datetime=original_time,  # Gaming: original was ~20h away
    )
    rescheduled_booking.payment_status = "authorized"
    db.flush()

    # Step 3: Student tries to cancel the rescheduled booking (now >24h away)
    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.capture_payment_intent") as mock_capture, \
         patch("app.services.stripe_service.StripeService.reverse_transfer") as mock_reverse, \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit, \
         patch("app.repositories.payment_repository.PaymentRepository.create_payment_event"):
        mock_capture.return_value = {
            "transfer_id": "tr_x",
            "amount_received": 10000,
            "transfer_amount": 8800,
        }
        result = service.cancel_booking(rescheduled_booking.id, user=student, reason="test")

    # Step 4: Verify the loophole is CLOSED
    assert result.status == BookingStatus.CANCELLED

    # CRITICAL ASSERTION: Settlement outcome should reflect credit, not release.
    assert result.payment_status == "settled", (
        "LOOPHOLE NOT CLOSED! Rescheduled booking got full release instead of credit"
    )

    # Verify credit was issued
    mock_credit.assert_called_once()
    credit_kwargs = mock_credit.call_args.kwargs
    assert credit_kwargs["amount_cents"] == 10000  # Lesson price
    assert credit_kwargs["user_id"] == student.id

    # Verify PI was captured and transfer reversed (credit-only, not release)
    mock_capture.assert_called_once()
    mock_reverse.assert_called_once()


def test_rescheduled_early_then_cancel_over_24h_gets_refund(db: Session):
    """LEGITIMATE SCENARIO: Early reschedule cancelled >24h before should get CARD REFUND.

    Part 4b Fair Policy - This proves the fair policy works:
    1. Student has a booking next Saturday 2pm (5 days away, >24h window)
    2. Student reschedules to next Wednesday (legitimate - no gaming)
    3. Student cancels >24h before new booking
    4. Result: CARD REFUND (not credit) - fair treatment for legitimate reschedule

    The key difference from gaming: original_lesson_datetime was >24h away when rescheduled.
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Original booking was 5 days out (>24h, NOT in penalty window) = LEGITIMATE scenario
    original_time = datetime.now() + timedelta(days=5)
    original_time = original_time.replace(minute=0, second=0, microsecond=0)
    if (original_time + timedelta(hours=1)).date() != original_time.date():
        original_time = (original_time + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    original_booking = _create_booking(db, student, instructor, svc, original_time)
    original_booking.status = BookingStatus.CANCELLED  # Simulate it was cancelled via reschedule
    db.flush()

    # New booking is 7 days out (>24h)
    new_time = datetime.combine(date.today() + timedelta(days=7), time(14, 0))
    # CRITICAL: original_lesson_datetime shows this was a LEGITIMATE early reschedule
    # (original was >24h away = ~120 hours, so NOT gaming)
    rescheduled_booking = _create_rescheduled_booking(
        db, student, instructor, svc, new_time, original_booking.id,
        original_lesson_datetime=original_time,  # Legitimate: original was ~5 days away
    )

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.cancel_payment_intent") as mock_cancel, \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit, \
         patch("app.repositories.payment_repository.PaymentRepository.create_payment_event"):
        result = service.cancel_booking(rescheduled_booking.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED

    # CRITICAL: Settlement outcome should reflect card refund, not credit.
    # This is the fair part of the policy - legitimate early reschedules are NOT penalized
    assert result.payment_status == "settled", (
        "FAIR POLICY BROKEN! Legitimate early reschedule should get card refund, not credit"
    )

    # Verify PI was cancelled for refund
    mock_cancel.assert_called_once()

    # Verify NO credit was issued (card refund, not credit)
    mock_credit.assert_not_called()


def test_legitimate_reschedule_cancel_after_original_passed(db: Session):
    """SCENARIO C: Legitimate reschedule, cancel AFTER original lesson time passed.

    This test proves the fix works correctly when:
    - Monday: Student has lesson Saturday (5 days away)
    - Monday: Student reschedules to next Wednesday (LEGITIMATE - was >24h out)
    - Sunday: Student cancels (Saturday has now PASSED - original is in the past!)
    - Should get: CARD REFUND (not credit-only)

    The key: At reschedule time (Monday), student was 5 days from Saturday.
    Even though Saturday is now in the past, this was a legitimate reschedule.

    BUG THIS CATCHES: If we compare original_lesson_datetime to NOW instead of
    to created_at (reschedule time), the original being in the past would wrongly
    trigger gaming detection.
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Create an actual original booking for FK constraint
    # This represents the "Saturday" booking that was rescheduled
    saturday_booking_time = datetime.now() - timedelta(days=1)  # Saturday (now in the past!)
    saturday_booking_time = saturday_booking_time.replace(hour=14, minute=0, second=0, microsecond=0)
    original_booking = _create_booking(db, student, instructor, svc, saturday_booking_time)
    original_booking.status = BookingStatus.CANCELLED  # Cancelled via reschedule
    db.flush()

    # New booking is next Wednesday (5 days from now, >24h)
    wednesday_lesson_time = datetime.combine(date.today() + timedelta(days=5), time(14, 0))

    # Create the rescheduled booking with a PAST created_at to simulate:
    # "Reschedule happened on Monday" (6 days ago)
    # At that time, Saturday was 5 days away (LEGITIMATE - >24h)
    monday_reschedule_time = datetime.now() - timedelta(days=6)

    rescheduled_booking = _create_rescheduled_booking(
        db, student, instructor, svc, wednesday_lesson_time, original_booking.id,
        original_lesson_datetime=saturday_booking_time,  # Saturday lesson time
    )
    # Manually set created_at to simulate the reschedule happened on Monday
    rescheduled_booking.created_at = monday_reschedule_time
    db.flush()

    # Verify test setup: original was 5 days from reschedule time (LEGITIMATE)
    hours_at_reschedule = (saturday_booking_time - monday_reschedule_time).total_seconds() / 3600
    assert hours_at_reschedule > 24, f"Test setup error: original should be >24h from reschedule, got {hours_at_reschedule}h"

    # Verify: original is NOW in the past (this is what would break old logic)
    hours_from_now = (saturday_booking_time - datetime.now()).total_seconds() / 3600
    assert hours_from_now < 0, f"Test setup error: original should be in the past, got {hours_from_now}h"

    service = BookingService(db)

    with patch("app.services.stripe_service.StripeService.cancel_payment_intent") as mock_cancel, \
         patch("app.repositories.payment_repository.PaymentRepository.create_platform_credit") as mock_credit, \
         patch("app.repositories.payment_repository.PaymentRepository.create_payment_event"):
        result = service.cancel_booking(rescheduled_booking.id, user=student, reason="test")

    assert result.status == BookingStatus.CANCELLED

    # CRITICAL: Settlement outcome should reflect card refund, not credit.
    # Even though original_lesson_datetime is in the past NOW, at RESCHEDULE TIME
    # the original was >24h away (5 days), so this was a legitimate reschedule.
    assert result.payment_status == "settled", (
        "BUG! Legitimate reschedule wrongly flagged as gaming because original is now in past. "
        f"Original was {hours_at_reschedule:.1f}h from reschedule time (LEGITIMATE), "
        f"but {hours_from_now:.1f}h from cancel time (past). Fix: use created_at, not now."
    )

    # Verify PI was cancelled for refund
    mock_cancel.assert_called_once()

    # Verify NO credit was issued (card refund, not credit)
    mock_credit.assert_not_called()


# =============================================================================
# Part 5: Block Second Reschedule Tests
# =============================================================================


def test_first_reschedule_allowed(db: Session):
    """PART 5: First reschedule should be allowed.

    A booking that was NOT created via reschedule (rescheduled_from_booking_id is None)
    should pass the validate_reschedule_allowed check.
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Create original booking (not from a reschedule)
    when = datetime.combine(date.today() + timedelta(days=3), time(14, 0))
    booking = _create_booking(db, student, instructor, svc, when)

    # Confirm booking is not from a reschedule
    assert booking.rescheduled_from_booking_id is None

    service = BookingService(db)

    # Should NOT raise - first reschedule is allowed
    service.validate_reschedule_allowed(booking)


def test_second_reschedule_blocked(db: Session):
    """PART 5: Second reschedule should be blocked.

    A booking that was created via reschedule (rescheduled_from_booking_id is set)
    should raise BusinessRuleException when trying to reschedule again.
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Create original booking
    when = datetime.combine(date.today() + timedelta(days=3), time(14, 0))
    original_booking = _create_booking(db, student, instructor, svc, when)

    # Create "rescheduled" booking (simulating late reschedule use)
    rescheduled_when = datetime.combine(date.today() + timedelta(days=5), time(15, 0))
    rescheduled_booking = _create_booking(db, student, instructor, svc, rescheduled_when)
    rescheduled_booking.rescheduled_from_booking_id = original_booking.id
    _upsert_reschedule(db, rescheduled_booking.id, late_reschedule_used=True)
    db.flush()

    service = BookingService(db)

    # Should raise BusinessRuleException - second reschedule blocked
    with pytest.raises(BusinessRuleException) as exc_info:
        service.validate_reschedule_allowed(rescheduled_booking)

    assert exc_info.value.code == "reschedule_limit_reached"


def test_second_reschedule_error_message(db: Session):
    """PART 5: Error message should guide user to cancel and rebook.

    The error message should clearly tell the user:
    - They've already rescheduled this booking
    - They need to cancel (for credit) and book a new lesson
    """
    instructor, profile, svc = _create_instructor_with_service(db)
    student = _create_student(db)

    # Create original booking
    when = datetime.combine(date.today() + timedelta(days=3), time(14, 0))
    original_booking = _create_booking(db, student, instructor, svc, when)

    # Create "rescheduled" booking (simulating late reschedule use)
    rescheduled_when = datetime.combine(date.today() + timedelta(days=5), time(15, 0))
    rescheduled_booking = _create_booking(db, student, instructor, svc, rescheduled_when)
    rescheduled_booking.rescheduled_from_booking_id = original_booking.id
    _upsert_reschedule(db, rescheduled_booking.id, late_reschedule_used=True)
    db.flush()

    service = BookingService(db)

    with pytest.raises(BusinessRuleException) as exc_info:
        service.validate_reschedule_allowed(rescheduled_booking)

    error_message = exc_info.value.message

    # Verify the message contains key guidance
    assert "late reschedule" in error_message.lower()
    assert "cancel" in error_message.lower()
    assert "book a new lesson" in error_message.lower()
