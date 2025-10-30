"""Unit tests for PricingService pricing calculations."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

import pytest

from app.core.exceptions import BusinessRuleException
from app.models.booking import Booking, BookingStatus
from app.schemas.pricing_preview import PricingPreviewIn
from app.services.config_service import DEFAULT_PRICING_CONFIG, ConfigService
from app.services.pricing_service import PricingService

try:  # pragma: no cover - allow running from backend/ root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_booking(
    *,
    db,
    instructor,
    student,
    service,
    hourly_rate: Decimal | float,
    duration_minutes: int = 60,
    location_type: str = "student_home",
    status: BookingStatus = BookingStatus.CONFIRMED,
    completed_at: datetime | None = None,
    offset_index: Optional[int] = None,
) -> Booking:
    """Persist and return a booking tailored for pricing tests."""

    hourly_rate_decimal = Decimal(str(hourly_rate)).quantize(Decimal("0.01"))
    start_time = time(10, 0)
    end_dt = datetime.combine(date.today(), start_time) + timedelta(minutes=duration_minutes)
    total_price = (
        hourly_rate_decimal * Decimal(duration_minutes) / Decimal(60)
    ).quantize(Decimal("0.01"))

    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
       instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=date.today(),
        start_time=start_time,
        end_time=end_dt.time(),
        service_name="Test Service",
        hourly_rate=hourly_rate_decimal,
        total_price=total_price,
        duration_minutes=duration_minutes,
        status=status,
        location_type=location_type,
        offset_index=offset_index,
    )

    if status is BookingStatus.COMPLETED:
        booking.completed_at = completed_at or datetime.now(timezone.utc)
        db.flush()

    db.refresh(booking)
    return booking


@pytest.fixture
def pricing_service(db):
    return PricingService(db)


@pytest.fixture
def instructor_service(db, test_instructor):
    db.refresh(test_instructor)
    profile = test_instructor.instructor_profile
    assert profile is not None, "Test instructor must have an instructor profile"
    db.refresh(profile)
    service = profile.instructor_services[0]
    db.refresh(service)
    return service


def test_pricing_service_enforces_price_floor(db, pricing_service, test_instructor, test_student, instructor_service):
    """Ensure in-person private bookings below the floor are rejected."""

    low_rate_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("79.99"),
    )

    with pytest.raises(BusinessRuleException) as exc:
        pricing_service.compute_booking_pricing(low_rate_booking.id)

    assert exc.value.code == "PRICE_BELOW_FLOOR"
    assert "Minimum price for a in-person 60-minute private session" in exc.value.message

    valid_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("80.00"),
        offset_index=1,
    )

    result = pricing_service.compute_booking_pricing(valid_booking.id)
    assert result["base_price_cents"] == 8000


def test_pricing_service_enforces_prorated_in_person_floor(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    low_rate_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("79.99"),
        duration_minutes=45,
    )

    with pytest.raises(BusinessRuleException) as exc:
        pricing_service.compute_booking_pricing(low_rate_booking.id)

    assert exc.value.code == "PRICE_BELOW_FLOOR"
    assert "45-minute" in exc.value.message

    valid_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("80.00"),
        duration_minutes=45,
        offset_index=1,
    )

    result = pricing_service.compute_booking_pricing(valid_booking.id)
    assert result["base_price_cents"] == 6000


def test_pricing_service_enforces_remote_floor(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    remote_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("59.98"),
        duration_minutes=30,
        location_type="online",
    )

    with pytest.raises(BusinessRuleException) as exc:
        pricing_service.compute_booking_pricing(remote_booking.id)

    assert exc.value.code == "PRICE_BELOW_FLOOR"
    assert "remote 30-minute" in exc.value.message

    valid_remote = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("60.00"),
        duration_minutes=30,
        location_type="online",
        offset_index=1,
    )

    result = pricing_service.compute_booking_pricing(valid_remote.id)
    assert result["base_price_cents"] == 3000


def test_pricing_service_detects_remote_by_meeting_location(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    """Neutral location type should defer to meeting location when it signals remote."""

    remote_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("50.00"),
        location_type="neutral",
    )

    remote_booking.meeting_location = "Online session"
    db.add(remote_booking)
    db.commit()
    db.refresh(remote_booking)

    with pytest.raises(BusinessRuleException) as exc:
        pricing_service.compute_booking_pricing(remote_booking.id)

    assert exc.value.code == "PRICE_BELOW_FLOOR"
    assert "remote 60-minute private session" in exc.value.message
    assert exc.value.details.get("modality") == "remote"
    assert exc.value.details.get("required_floor_cents") == 6000


def test_pricing_service_tier_pct_at_five_completed_sessions(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    """Exactly five recent completions should maintain the 12% tier."""

    profile = test_instructor.instructor_profile
    profile.current_tier_pct = Decimal("15.00")
    db.add(profile)
    db.flush()

    for offset in range(5):
        _create_booking(
            db=db,
            instructor=test_instructor,
            student=test_student,
            service=instructor_service,
            hourly_rate=Decimal("90.00"),
            status=BookingStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc) - timedelta(days=offset),
            offset_index=offset * 70,
        )

    upcoming_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("90.00"),
        offset_index=400,
    )

    result = pricing_service.compute_booking_pricing(upcoming_booking.id)
    assert result["instructor_tier_pct"] == pytest.approx(0.12)


def test_pricing_service_tier_pct_at_eleven_completed_sessions(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    """Eleven recent completions should maintain the 10% tier."""

    profile = test_instructor.instructor_profile
    profile.current_tier_pct = Decimal("15.00")
    db.add(profile)
    db.flush()

    for offset in range(11):
        _create_booking(
            db=db,
            instructor=test_instructor,
            student=test_student,
            service=instructor_service,
            hourly_rate=Decimal("95.00"),
            status=BookingStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc) - timedelta(days=offset),
            offset_index=offset * 70,
        )

    upcoming_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("95.00"),
        offset_index=900,
    )

    result = pricing_service.compute_booking_pricing(upcoming_booking.id)
    assert result["instructor_tier_pct"] == pytest.approx(0.10)


def test_pricing_preview_returns_tier_pct_float_for_booking(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("90.00"),
    )

    result = pricing_service.compute_booking_pricing(booking.id)

    assert isinstance(result["instructor_tier_pct"], float)
    assert result["instructor_tier_pct"] >= 0


@pytest.mark.usefixtures("disable_price_floors")
def test_pricing_preview_returns_tier_pct_float_for_quote(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    payload = PricingPreviewIn(
        instructor_id=str(test_instructor.id),
        instructor_service_id=str(instructor_service.id),
        booking_date=date.today().strftime("%Y-%m-%d"),
        start_time="10:00",
        selected_duration=60,
        location_type="remote",
        meeting_location="Online",
        applied_credit_cents=0,
    )

    result = pricing_service.compute_quote_pricing(payload, student_id=str(test_student.id))

    assert isinstance(result["instructor_tier_pct"], float)
    assert result["instructor_tier_pct"] >= 0


@pytest.mark.usefixtures("disable_price_floors")
def test_inactivity_reset_to_entry_tier(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    """If the instructor has been inactive past the reset window, fall back to entry tier."""

    profile = test_instructor.instructor_profile
    profile.current_tier_pct = Decimal("10.00")
    db.add(profile)
    db.flush()

    _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("90.00"),
        status=BookingStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc) - timedelta(days=120),
    )

    payload = PricingPreviewIn(
        instructor_id=str(test_instructor.id),
        instructor_service_id=str(instructor_service.id),
        booking_date=date.today().strftime("%Y-%m-%d"),
        start_time="11:00",
        selected_duration=60,
        location_type="remote",
        meeting_location="Online",
        applied_credit_cents=0,
    )

    result = pricing_service.compute_quote_pricing(payload, student_id=str(test_student.id))

    assert result["instructor_tier_pct"] == pytest.approx(0.15)


def test_pricing_service_respects_config_overrides(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
):
    config_service = ConfigService(db)
    original_config, _ = config_service.get_pricing_config()
    updated_config = deepcopy(original_config)
    updated_config["price_floor_cents"]["private_remote"] = 6500
    config_service.set_pricing_config(updated_config)
    db.commit()

    below_new_floor = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("64.99"),
        location_type="online",
        offset_index=10,
    )

    with pytest.raises(BusinessRuleException) as exc:
        pricing_service.compute_booking_pricing(below_new_floor.id)

    assert exc.value.code == "PRICE_BELOW_FLOOR"
    assert "$65.00" in exc.value.message

    meets_new_floor = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("65.00"),
        location_type="online",
        offset_index=11,
    )

    result = pricing_service.compute_booking_pricing(meets_new_floor.id)
    assert result["base_price_cents"] == 6500

    config_service.set_pricing_config(original_config)
    db.commit()


def test_pricing_service_promotes_to_lower_tier(db, pricing_service, test_instructor, test_student, instructor_service):
    """Instructor tier should promote immediately when hitting a threshold."""

    profile = test_instructor.instructor_profile
    profile.current_tier_pct = Decimal("15.00")
    db.add(profile)
    db.flush()

    for offset in range(4):
        completed_at = datetime.now(timezone.utc) - timedelta(days=offset)
        _create_booking(
            db=db,
            instructor=test_instructor,
            student=test_student,
            service=instructor_service,
            hourly_rate=Decimal("90.00"),
            status=BookingStatus.COMPLETED,
            completed_at=completed_at,
            offset_index=offset * 70,
        )

    pending_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("90.00"),
        offset_index=450,
    )

    result = pricing_service.compute_booking_pricing(pending_booking.id)
    assert result["instructor_tier_pct"] == pytest.approx(0.12)


def test_pricing_service_limits_tier_demotion(db, pricing_service, test_instructor, test_student, instructor_service):
    """Instructor tier should only demote by a single tier per session."""

    profile = test_instructor.instructor_profile
    profile.current_tier_pct = Decimal("10.00")
    db.add(profile)
    db.flush()

    for offset in range(2):
        completed_at = datetime.now(timezone.utc) - timedelta(days=offset)
        _create_booking(
            db=db,
            instructor=test_instructor,
            student=test_student,
            service=instructor_service,
            hourly_rate=Decimal("100.00"),
            status=BookingStatus.COMPLETED,
            completed_at=completed_at,
            offset_index=offset * 70,
        )

    upcoming_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("100.00"),
        offset_index=420,
    )

    result = pricing_service.compute_booking_pricing(upcoming_booking.id)
    assert result["instructor_tier_pct"] == pytest.approx(0.12)


def test_pricing_service_handles_large_credit_top_up(db, pricing_service, test_instructor, test_student, instructor_service):
    """Credits exceeding platform share should trigger a top-up transfer."""

    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("100.00"),
    )

    response = pricing_service.compute_booking_pricing(
        booking_id=booking.id,
        applied_credit_cents=30000,
    )

    assert response["application_fee_cents"] == 0
    assert response["student_pay_cents"] == 0
    assert response["top_up_transfer_cents"] == response["target_instructor_payout_cents"]


def test_pricing_service_outputs_integer_cents(db, pricing_service, test_instructor, test_student, instructor_service):
    """All monetary outputs should be integer cents to avoid float drift."""

    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("123.45"),
        duration_minutes=45,
    )

    result = pricing_service.compute_booking_pricing(booking.id)

    monetary_keys = [
        "base_price_cents",
        "student_fee_cents",
        "instructor_commission_cents",
        "target_instructor_payout_cents",
        "credit_applied_cents",
        "student_pay_cents",
        "application_fee_cents",
        "top_up_transfer_cents",
    ]

    for key in monetary_keys:
        assert isinstance(result[key], int)

    assert isinstance(result["line_items"], list)
    assert all(isinstance(item["amount_cents"], int) for item in result["line_items"])
@pytest.fixture(autouse=True)
def _restore_default_price_floors(db):
    config_service = ConfigService(db)
    config_service.set_pricing_config(deepcopy(DEFAULT_PRICING_CONFIG))
    db.commit()
    yield
