"""Unit tests for PricingService pricing calculations."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
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
    location_type: str = "student_location",
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
        location_type="neutral_location",
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


def test_resolve_modality_prefers_service_location_types():
    booking = SimpleNamespace(
        location_type="",
        meeting_location="",
        instructor_service=SimpleNamespace(location_types=["ONLINE"]),
    )

    assert PricingService._resolve_modality(booking) == "remote"


def test_resolve_modality_falls_back_to_meeting_location():
    booking = SimpleNamespace(
        location_type="unknown",
        meeting_location="Zoom online session",
        instructor_service=SimpleNamespace(location_types=[]),
    )

    assert PricingService._resolve_modality(booking) == "remote"


def test_resolve_modality_defaults_to_in_person():
    booking = SimpleNamespace(
        location_type="",
        meeting_location="",
        instructor_service=SimpleNamespace(location_types=None),
    )

    assert PricingService._resolve_modality(booking) == "in_person"


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
        location_type="online",
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
        location_type="online",
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
    """Credits exceeding lesson price trigger top-up transfer (Part 6 compliant).

    With Part 6: Credits can only cover lesson price, never the platform fee.
    - $100 lesson, $300 credit requested
    - Credit applied: $100 (capped at lesson price)
    - Student pays: $12 (fee only - minimum card charge)
    - Application fee: $0 (credit reduces it below zero)
    - Top-up needed: instructor payout - student payment
    """
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

    # Part 6: Credit capped at lesson price ($100)
    assert response["credit_applied_cents"] == 10000

    # Part 6: Student always pays platform fee ($12)
    assert response["student_fee_cents"] == 1200
    assert response["student_pay_cents"] == 1200  # Fee only

    # Application fee reduced to 0 by credit
    assert response["application_fee_cents"] == 0

    # Top-up needed: target_payout - student_pay
    target_payout = response["target_instructor_payout_cents"]
    student_pay = response["student_pay_cents"]
    assert response["top_up_transfer_cents"] == target_payout - student_pay


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
        "instructor_platform_fee_cents",
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


def test_founding_instructor_gets_founding_rate(
    db, pricing_service, test_instructor, test_student, instructor_service
):
    """Founding instructors should use the founding rate regardless of tier."""

    profile = test_instructor.instructor_profile
    profile.is_founding_instructor = True
    profile.current_tier_pct = 15
    db.flush()

    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("80.00"),
        duration_minutes=60,
    )

    config = deepcopy(DEFAULT_PRICING_CONFIG)
    config["founding_instructor_rate_pct"] = 0.08
    rate = pricing_service._resolve_instructor_tier_pct(
        booking=booking, instructor_profile=profile, pricing_config=config
    )

    assert rate == Decimal("0.0800")


def test_regular_instructor_uses_tier_rate(
    db, pricing_service, test_instructor, test_student, instructor_service
):
    """Non-founding instructors should use tier-based rates."""

    profile = test_instructor.instructor_profile
    profile.is_founding_instructor = False
    profile.current_tier_pct = 15
    db.flush()

    completed_booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("80.00"),
        duration_minutes=60,
        status=BookingStatus.COMPLETED,
    )

    config = deepcopy(DEFAULT_PRICING_CONFIG)
    rate = pricing_service._resolve_instructor_tier_pct(
        booking=completed_booking, instructor_profile=profile, pricing_config=config
    )

    assert rate == Decimal("0.1500")


def test_founding_instructor_immune_to_tier_update(db, pricing_service, test_instructor):
    """Founding instructors should not have their tier updated."""
    profile = test_instructor.instructor_profile
    original_tier = profile.current_tier_pct
    original_eval = profile.last_tier_eval_at
    profile.is_founding_instructor = True
    db.flush()

    result = pricing_service.update_instructor_tier(profile, new_tier_pct=0.10)

    assert result is False
    assert profile.current_tier_pct == original_tier
    assert profile.last_tier_eval_at == original_eval


def test_regular_instructor_tier_can_be_updated(db, pricing_service, test_instructor):
    """Non-founding instructors should allow tier updates."""
    profile = test_instructor.instructor_profile
    profile.is_founding_instructor = False
    db.flush()

    result = pricing_service.update_instructor_tier(profile, new_tier_pct=0.10)

    assert result is True
    assert float(profile.current_tier_pct) == pytest.approx(10.0)
    assert profile.last_tier_eval_at is not None


@pytest.fixture(autouse=True)
def _restore_default_price_floors(db):
    config_service = ConfigService(db)
    config_service.set_pricing_config(deepcopy(DEFAULT_PRICING_CONFIG))
    db.commit()
    yield


# =============================================================================
# Part 6: Credits Apply to Lesson Price Only Tests
# =============================================================================


def test_credits_capped_at_lesson_price(db, pricing_service, test_instructor, test_student, instructor_service):
    """PART 6: Credits exceeding lesson price should be capped.

    Scenario: $200 credit, $120 lesson ($134.40 total)
    - Credit applied: $120 (capped at lesson price)
    - Card charged: $14.40 (platform fee)
    - Remaining credit: $80 (not consumed)
    """
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("120.00"),  # $120/hr for 60 min = $120 lesson
    )

    # Try to apply $200 credit (more than lesson price)
    response = pricing_service.compute_booking_pricing(
        booking_id=booking.id,
        applied_credit_cents=20000,  # $200 in cents
    )

    # Credits should be capped at lesson price ($120)
    assert response["base_price_cents"] == 12000  # $120
    assert response["credit_applied_cents"] == 12000  # Capped at lesson price
    # Student pays platform fee only (12% of $120 = $14.40)
    assert response["student_fee_cents"] == 1440
    assert response["student_pay_cents"] == 1440  # Fee only, lesson covered by credit


def test_partial_credit_application(db, pricing_service, test_instructor, test_student, instructor_service):
    """PART 6: Partial credits should reduce lesson price, fee still charged.

    Scenario: $50 credit, $120 lesson ($134.40 total)
    - Credit applied: $50
    - Card charged: $84.40 ($70 lesson + $14.40 fee)
    """
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("120.00"),
    )

    response = pricing_service.compute_booking_pricing(
        booking_id=booking.id,
        applied_credit_cents=5000,  # $50 in cents
    )

    assert response["base_price_cents"] == 12000  # $120
    assert response["credit_applied_cents"] == 5000  # Full $50 applied
    assert response["student_fee_cents"] == 1440  # 12% of $120
    # Student pays: ($120 - $50) + $14.40 = $84.40
    assert response["student_pay_cents"] == 8440


def test_zero_credits_full_charge(db, pricing_service, test_instructor, test_student, instructor_service):
    """PART 6: Zero credits means student pays full amount.

    Scenario: $0 credit, $120 lesson
    - Card charged: $134.40 (lesson + fee)
    """
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("120.00"),
    )

    response = pricing_service.compute_booking_pricing(
        booking_id=booking.id,
        applied_credit_cents=0,
    )

    assert response["base_price_cents"] == 12000
    assert response["credit_applied_cents"] == 0
    assert response["student_fee_cents"] == 1440
    # Student pays full: $120 + $14.40 = $134.40
    assert response["student_pay_cents"] == 13440


def test_credits_equal_lesson_price(db, pricing_service, test_instructor, test_student, instructor_service):
    """PART 6: Credits exactly equal to lesson price should cover lesson only.

    Scenario: $120 credit, $120 lesson
    - Credit applied: $120
    - Card charged: $14.40 (fee only)
    """
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("120.00"),
    )

    response = pricing_service.compute_booking_pricing(
        booking_id=booking.id,
        applied_credit_cents=12000,  # Exactly $120
    )

    assert response["base_price_cents"] == 12000
    assert response["credit_applied_cents"] == 12000  # Full lesson covered
    assert response["student_fee_cents"] == 1440
    # Student pays fee only: $14.40
    assert response["student_pay_cents"] == 1440


def test_minimum_card_charge_is_fee(db, pricing_service, test_instructor, test_student, instructor_service):
    """PART 6: Minimum card charge should always be the platform fee.

    No matter how large the credit, student_pay_cents >= student_fee_cents.
    """
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=Decimal("100.00"),
    )

    # Apply huge credit (10x lesson price)
    response = pricing_service.compute_booking_pricing(
        booking_id=booking.id,
        applied_credit_cents=100000,  # $1000 in cents
    )

    base_price = response["base_price_cents"]
    fee = response["student_fee_cents"]

    # Credit should be capped at lesson price
    assert response["credit_applied_cents"] == base_price

    # Student always pays at least the fee
    assert response["student_pay_cents"] >= fee
    assert response["student_pay_cents"] == fee  # Exactly the fee when lesson is covered


@pytest.mark.parametrize(
    "hourly_rate,credit_cents,expected_credit_applied,expected_student_pay",
    [
        # Case 1: Credit larger than lesson - capped at lesson, pay fee only
        (Decimal("100.00"), 15000, 10000, 1200),  # $150 credit, $100 lesson -> $12 fee only
        # Case 2: Credit smaller than lesson - full credit used
        (Decimal("100.00"), 5000, 5000, 6200),  # $50 credit, $100 lesson -> $50 + $12 = $62
        # Case 3: Zero credit - full payment
        (Decimal("100.00"), 0, 0, 11200),  # $0 credit, $100 lesson -> $112
        # Case 4: Credit exactly matches lesson
        (Decimal("80.00"), 8000, 8000, 960),  # $80 credit, $80 lesson -> $9.60 fee only
    ],
)
def test_credit_scenarios(
    db,
    pricing_service,
    test_instructor,
    test_student,
    instructor_service,
    hourly_rate,
    credit_cents,
    expected_credit_applied,
    expected_student_pay,
):
    """PART 6: Parametrized test for various credit scenarios."""
    booking = _create_booking(
        db=db,
        instructor=test_instructor,
        student=test_student,
        service=instructor_service,
        hourly_rate=hourly_rate,
    )

    response = pricing_service.compute_booking_pricing(
        booking_id=booking.id,
        applied_credit_cents=credit_cents,
    )

    assert response["credit_applied_cents"] == expected_credit_applied
    assert response["student_pay_cents"] == expected_student_pay
