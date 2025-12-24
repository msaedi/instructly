"""
Payout and earnings summary tests for StripeService.
"""

from datetime import datetime, time, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
import ulid

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.core.exceptions import ServiceException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.review import Review, ReviewStatus, ReviewTip
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService


@pytest.fixture
def stripe_service(db: Session) -> StripeService:
    config_service = ConfigService(db)
    pricing_service = PricingService(db)
    return StripeService(db, config_service=config_service, pricing_service=pricing_service)


@pytest.fixture
def test_user(db: Session) -> User:
    user = User(
        id=str(ulid.ULID()),
        email=f"student_{ulid.ULID()}@example.com",
        hashed_password="hashed",
        first_name="Student",
        last_name="User",
        zip_code="10001",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def test_instructor(db: Session) -> tuple[User, InstructorProfile, InstructorService]:
    user = User(
        id=str(ulid.ULID()),
        email=f"instructor_{ulid.ULID()}@example.com",
        hashed_password="hashed",
        first_name="Instructor",
        last_name="User",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(
        id=str(ulid.ULID()),
        user_id=user.id,
        bio="Payout instructor",
        years_experience=5,
    )
    db.add(profile)
    db.flush()

    category_ulid = str(ulid.ULID())
    category = (
        db.query(ServiceCategory)
        .filter_by(slug=f"payout-category-{category_ulid.lower()}")
        .first()
    )
    if not category:
        category = ServiceCategory(
            id=category_ulid,
            name="Payout Category",
            slug=f"payout-category-{category_ulid.lower()}",
            description="Payout category",
        )
        db.add(category)
        db.flush()

    service_ulid = str(ulid.ULID())
    catalog = (
        db.query(ServiceCatalog)
        .filter_by(slug=f"payout-service-{service_ulid.lower()}")
        .first()
    )
    if not catalog:
        catalog = ServiceCatalog(
            id=service_ulid,
            category_id=category.id,
            name="Payout Service",
            slug=f"payout-service-{service_ulid.lower()}",
            description="Payout service",
        )
        db.add(catalog)
        db.flush()

    service = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=120.00,
        is_active=True,
    )
    db.add(service)
    db.flush()

    return user, profile, service


@pytest.fixture
def test_booking(db: Session, test_user: User, test_instructor: tuple) -> Booking:
    instructor_user, _, instructor_service = test_instructor
    booking = Booking(
        id=str(ulid.ULID()),
        student_id=test_user.id,
        instructor_id=instructor_user.id,
        instructor_service_id=instructor_service.id,
        booking_date=datetime.now().date(),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_name="Payout Service",
        hourly_rate=120.00,
        total_price=120.00,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
    )
    db.add(booking)
    db.flush()
    return booking


@patch("stripe.Payout.create")
def test_request_instructor_instant_payout_success(
    mock_create, stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, profile, _ = test_instructor
    stripe_service.payment_repository.create_connected_account_record(
        profile.id, "acct_payout", onboarding_completed=True
    )

    mock_payout = MagicMock()
    mock_payout.id = "po_instant"
    mock_payout.status = "paid"
    mock_create.return_value = mock_payout

    result = stripe_service.request_instructor_instant_payout(user=user, amount_cents=5000)

    assert result.ok is True
    assert result.payout_id == "po_instant"
    assert result.status == "paid"


def test_request_instructor_instant_payout_missing_profile(
    stripe_service: StripeService, test_user: User
) -> None:
    with pytest.raises(ServiceException, match="Instructor profile not found"):
        stripe_service.request_instructor_instant_payout(user=test_user, amount_cents=5000)


def test_request_instructor_instant_payout_not_onboarded(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, _, _ = test_instructor
    with pytest.raises(ServiceException, match="not onboarded"):
        stripe_service.request_instructor_instant_payout(user=user, amount_cents=5000)


@patch("stripe.Account.modify")
def test_set_instructor_payout_schedule_success(
    mock_modify, stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, profile, _ = test_instructor
    stripe_service.payment_repository.create_connected_account_record(
        profile.id, "acct_sched", onboarding_completed=True
    )
    mock_modify.return_value = {"id": "acct_sched"}

    result = stripe_service.set_instructor_payout_schedule(
        user=user, monthly_anchor=15, interval="monthly"
    )

    assert result.ok is True
    assert result.account_id == "acct_sched"
    assert result.settings["interval"] == "monthly"


def test_set_instructor_payout_schedule_missing_profile(
    stripe_service: StripeService, test_user: User
) -> None:
    with pytest.raises(ServiceException, match="Instructor profile not found"):
        stripe_service.set_instructor_payout_schedule(
            user=test_user, monthly_anchor=None, interval="weekly"
        )


def test_set_instructor_payout_schedule_not_onboarded(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, _, _ = test_instructor
    with pytest.raises(ServiceException, match="not onboarded"):
        stripe_service.set_instructor_payout_schedule(user=user, monthly_anchor=None, interval="weekly")


def test_get_instructor_payout_history_totals(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    _, profile, _ = test_instructor
    repo = stripe_service.payment_repository
    repo.record_payout_event(
        instructor_profile_id=profile.id,
        stripe_account_id="acct_hist",
        payout_id="po_paid",
        amount_cents=1000,
        status="paid",
        arrival_date=None,
    )
    repo.record_payout_event(
        instructor_profile_id=profile.id,
        stripe_account_id="acct_hist",
        payout_id="po_pending",
        amount_cents=2000,
        status="pending",
        arrival_date=None,
    )
    repo.record_payout_event(
        instructor_profile_id=profile.id,
        stripe_account_id="acct_hist",
        payout_id="po_transit",
        amount_cents=3000,
        status="in_transit",
        arrival_date=None,
    )

    user = stripe_service.user_repository.get_by_id(profile.user_id)
    assert user is not None

    history = stripe_service.get_instructor_payout_history(user=user, limit=10)

    assert history.payout_count == 3
    assert history.total_paid_cents == 1000
    assert history.total_pending_cents == 5000


def test_get_instructor_payout_history_empty(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, profile, _ = test_instructor
    history = stripe_service.get_instructor_payout_history(user=user, limit=10)

    assert history.payout_count == 0
    assert history.total_paid_cents == 0
    assert history.total_pending_cents == 0


def test_get_instructor_payout_history_missing_profile(
    stripe_service: StripeService, test_user: User
) -> None:
    with pytest.raises(ServiceException, match="Instructor profile not found"):
        stripe_service.get_instructor_payout_history(user=test_user, limit=10)


def test_get_instructor_earnings(
    stripe_service: StripeService, test_booking: Booking
) -> None:
    context = stripe_service.build_charge_context(test_booking.id)
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_earnings",
        context.student_pay_cents,
        context.application_fee_cents,
        "succeeded",
    )

    earnings = stripe_service.get_instructor_earnings(test_booking.instructor_id)

    assert earnings["total_earned"] == (
        context.student_pay_cents - context.application_fee_cents
    )
    assert earnings["total_fees"] == context.application_fee_cents
    assert earnings["booking_count"] == 1


def test_get_platform_revenue_stats(
    stripe_service: StripeService, test_booking: Booking
) -> None:
    context = stripe_service.build_charge_context(test_booking.id)
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_revenue",
        context.student_pay_cents,
        context.application_fee_cents,
        "succeeded",
    )

    stats = stripe_service.get_platform_revenue_stats()

    assert stats["total_amount"] == context.student_pay_cents
    assert stats["total_fees"] == context.application_fee_cents
    assert stats["payment_count"] == 1


def test_get_platform_revenue_stats_error(stripe_service: StripeService) -> None:
    stripe_service.payment_repository.get_platform_revenue_stats = MagicMock(
        side_effect=Exception("db down")
    )

    with pytest.raises(ServiceException, match="Failed to get revenue stats"):
        stripe_service.get_platform_revenue_stats()


def test_get_instructor_earnings_error(stripe_service: StripeService) -> None:
    stripe_service.payment_repository.get_instructor_earnings = MagicMock(
        side_effect=Exception("db down")
    )

    with pytest.raises(ServiceException, match="Failed to get instructor earnings"):
        stripe_service.get_instructor_earnings("instructor_id")


def test_get_instructor_earnings_summary_includes_tips(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    instructor_user, profile, service = test_instructor
    repo = stripe_service.payment_repository

    repo.create_payment_record(
        test_booking.id,
        "pi_booking",
        amount=13440,
        application_fee=3240,
        status="succeeded",
    )
    repo.create_payment_record(
        test_booking.id,
        "pi_tip",
        amount=500,
        application_fee=0,
        status="processing",
    )

    review = Review(
        booking_id=test_booking.id,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        rating=5,
        review_text="Great",
        status=ReviewStatus.PUBLISHED,
        is_verified=True,
        booking_completed_at=datetime.now(timezone.utc),
    )
    stripe_service.db.add(review)
    stripe_service.db.flush()

    tip = ReviewTip(
        review_id=review.id,
        amount_cents=500,
        stripe_payment_intent_id="pi_tip",
        status="succeeded",
        processed_at=datetime.now(timezone.utc),
    )
    stripe_service.db.add(tip)
    stripe_service.db.flush()

    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    assert summary.total_tips == 500
    assert summary.total_lesson_value == 12000
    assert summary.total_platform_fees > 0
    assert summary.invoices

    invoice = summary.invoices[0]
    assert invoice.lesson_price_cents == 12000
    assert invoice.platform_fee_cents > 0
    assert invoice.instructor_share_cents == 10200
    assert invoice.status == "paid"


def test_get_instructor_earnings_summary_excludes_pending(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    instructor_user, profile, _ = test_instructor
    repo = stripe_service.payment_repository

    repo.create_payment_record(
        test_booking.id,
        "pi_succeeded",
        amount=10000,
        application_fee=1500,
        status="succeeded",
    )
    repo.create_payment_record(
        test_booking.id,
        "pi_pending",
        amount=10000,
        application_fee=1500,
        status="requires_capture",
    )

    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    assert len(summary.invoices) == 1


def test_get_instructor_earnings_summary_missing_profile(
    stripe_service: StripeService, test_user: User
) -> None:
    with pytest.raises(ServiceException, match="Instructor profile not found"):
        stripe_service.get_instructor_earnings_summary(user=test_user)


def test_get_instructor_earnings_summary_handles_missing_booking_and_summary_errors(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, _, _ = test_instructor
    bad_payment = MagicMock(
        booking=None,
        amount=0,
        application_fee=0,
        status="succeeded",
        created_at=datetime.now(timezone.utc),
        base_price_cents=None,
        instructor_tier_pct=None,
        instructor_payout_cents=None,
    )
    bad_booking = MagicMock(
        id="bk_bad",
        student=None,
        duration_minutes=60,
        hourly_rate="bad",
        service_name="Test Service",
        booking_date=datetime.now().date(),
        start_time=time(10, 0),
    )
    good_payment = MagicMock(
        booking=bad_booking,
        amount=1000,
        application_fee=100,
        status="succeeded",
        created_at=datetime.now(timezone.utc),
        base_price_cents=None,
        instructor_tier_pct=None,
        instructor_payout_cents=None,
    )

    with (
        patch.object(
            stripe_service.payment_repository,
            "get_instructor_payment_history",
            return_value=[bad_payment, good_payment],
        ),
        patch.object(
            stripe_service.config_service,
            "get_pricing_config",
            return_value=({"instructor_tiers": []}, None),
        ),
        patch.object(
            stripe_service,
            "get_instructor_earnings",
            return_value={
                "total_earned": 0,
                "total_fees": 0,
                "booking_count": 0,
                "average_earning": 0,
                "period_start": None,
                "period_end": None,
            },
        ),
        patch(
            "app.services.stripe_service.build_student_payment_summary",
            side_effect=Exception("boom"),
        ),
    ):
        summary = stripe_service.get_instructor_earnings_summary(user=user)

    assert len(summary.invoices) == 1


def test_get_instructor_earnings_summary_default_tier_when_missing_current(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    instructor_user, _, _ = test_instructor

    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_default_tier",
        amount=10000,
        application_fee=1500,
        status="succeeded",
    )

    with (
        patch.object(
            stripe_service.config_service,
            "get_pricing_config",
            return_value=({"instructor_tiers": [{"pct": 0.2}], "student_fee_pct": 0.12}, None),
        ),
        patch.object(
            stripe_service,
            "get_instructor_earnings",
            return_value={
                "total_earned": 0,
                "total_fees": 0,
                "booking_count": 0,
                "average_earning": 0,
                "period_start": None,
                "period_end": None,
            },
        ),
        patch(
            "app.services.stripe_service.build_student_payment_summary",
            return_value=MagicMock(tip_paid=0),
        ),
        patch.object(
            stripe_service.instructor_repository,
            "get_by_user_id",
            return_value=MagicMock(current_tier_pct=None),
        ),
    ):
        summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    assert summary.invoices[0].platform_fee_rate == pytest.approx(0.2)


def test_get_instructor_earnings_summary_handles_invalid_tier_and_tip(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    instructor_user, _, _ = test_instructor

    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_bad_tier",
        amount=10000,
        application_fee=1500,
        status="succeeded",
    )

    with (
        patch.object(
            stripe_service.config_service,
            "get_pricing_config",
            return_value=({"instructor_tiers": [{"pct": 0.15}], "student_fee_pct": 0.12}, None),
        ),
        patch.object(
            stripe_service,
            "get_instructor_earnings",
            return_value={
                "total_earned": 0,
                "total_fees": 0,
                "booking_count": 0,
                "average_earning": 0,
                "period_start": None,
                "period_end": None,
            },
        ),
        patch(
            "app.services.stripe_service.build_student_payment_summary",
            return_value=MagicMock(tip_paid="bad"),
        ),
        patch.object(
            stripe_service.instructor_repository,
            "get_by_user_id",
            return_value=MagicMock(current_tier_pct="bad"),
        ),
    ):
        summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    assert summary.total_tips == 0
    assert summary.invoices[0].platform_fee_rate == pytest.approx(0.15)


def test_get_instructor_earnings_summary_uses_actual_instructor_tier(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    # FIX: use instructor_profile.current_tier_pct when present for platform fee fields.
    instructor_user, profile, _ = test_instructor
    stripe_service.instructor_repository.update(profile.id, current_tier_pct=0.10)

    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_tier",
        amount=10000,
        application_fee=1500,
        status="succeeded",
    )

    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    invoice = summary.invoices[0]
    assert invoice.platform_fee_rate == pytest.approx(0.10)


def test_get_instructor_earnings_summary_uses_configured_student_fee_pct(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    """Student fee percent should come from ConfigService (admin pricing config)."""
    instructor_user, _, _ = test_instructor
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_student_fee_config",
        amount=10000,
        application_fee=1500,
        status="succeeded",
    )

    pricing_config, _ = stripe_service.config_service.get_pricing_config()
    pricing_config["student_fee_pct"] = 0.2
    stripe_service.config_service.set_pricing_config(pricing_config)

    with (
        patch.object(
            stripe_service,
            "get_instructor_earnings",
            return_value={
                "total_earned": 0,
                "total_fees": 0,
                "booking_count": 0,
                "average_earning": 0,
                "period_start": None,
                "period_end": None,
            },
        ),
        patch(
            "app.services.stripe_service.build_student_payment_summary",
            return_value=MagicMock(tip_paid=0),
        ),
    ):
        summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    invoice = summary.invoices[0]
    expected_fee_cents = int(Decimal(invoice.lesson_price_cents) * Decimal("0.2"))
    assert invoice.student_fee_cents == expected_fee_cents


def test_get_instructor_earnings_summary_defaults_student_fee_pct_when_missing(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    instructor_user, _, _ = test_instructor
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_student_fee_default",
        amount=10000,
        application_fee=1500,
        status="succeeded",
    )

    with (
        patch.object(
            stripe_service.config_service,
            "get_pricing_config",
            return_value=({"instructor_tiers": [{"pct": 0.15}]}, None),
        ),
        patch.object(
            stripe_service,
            "get_instructor_earnings",
            return_value={
                "total_earned": 0,
                "total_fees": 0,
                "booking_count": 0,
                "average_earning": 0,
                "period_start": None,
                "period_end": None,
            },
        ),
        patch(
            "app.services.stripe_service.build_student_payment_summary",
            return_value=MagicMock(tip_paid=0),
        ),
    ):
        summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    invoice = summary.invoices[0]
    expected_fee_cents = int(
        Decimal(invoice.lesson_price_cents) * Decimal(str(PRICING_DEFAULTS["student_fee_pct"]))
    )
    assert invoice.student_fee_cents == expected_fee_cents


# ========== Part 9: Earnings Metadata Tests ==========


def test_earnings_summary_reads_from_db_columns(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    """Earnings should read directly from DB columns when available."""
    instructor_user, profile, _ = test_instructor

    # Create payment with earnings metadata
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_db_columns",
        amount=13440,  # Total student paid
        application_fee=1440,  # 12% of 12000
        status="succeeded",
        base_price_cents=12000,  # Stored lesson price
        instructor_tier_pct=Decimal("0.12"),  # Stored tier
        instructor_payout_cents=10560,  # Stored payout (12000 - 1440)
    )

    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    assert len(summary.invoices) == 1
    invoice = summary.invoices[0]

    # These should come directly from DB, not computed
    assert invoice.lesson_price_cents == 12000
    assert invoice.platform_fee_rate == pytest.approx(0.12)
    assert invoice.instructor_share_cents == 10560


def test_earnings_summary_fallback_for_legacy_payments(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    """Legacy payments without metadata should use computed fallback values."""
    instructor_user, profile, _ = test_instructor

    # Create payment WITHOUT earnings metadata (legacy style)
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_legacy",
        amount=13440,
        application_fee=1440,
        status="succeeded",
        # No base_price_cents, instructor_tier_pct, instructor_payout_cents
    )

    with (
        patch.object(
            stripe_service,
            "get_instructor_earnings",
            return_value={
                "total_earned": 0,
                "total_fees": 0,
                "booking_count": 0,
                "average_earning": 0,
                "period_start": None,
                "period_end": None,
            },
        ),
        patch(
            "app.services.stripe_service.build_student_payment_summary",
            return_value=MagicMock(tip_paid=0),
        ),
    ):
        summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    assert len(summary.invoices) == 1
    invoice = summary.invoices[0]

    # Fallback: lesson_price computed from hourly_rate * duration
    # test_booking: hourly_rate=120, duration=60min -> 12000 cents
    assert invoice.lesson_price_cents == 12000

    # Fallback: instructor_share = amount - application_fee
    assert invoice.instructor_share_cents == 13440 - 1440


def test_founding_instructor_8pct_tier_from_db(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    """Founding instructor 8% tier should display correctly when stored in DB."""
    instructor_user, profile, _ = test_instructor

    # Create payment with 8% founding tier
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_founding",
        amount=13440,
        application_fee=960,  # 8% of 12000
        status="succeeded",
        base_price_cents=12000,
        instructor_tier_pct=Decimal("0.08"),  # Founding rate
        instructor_payout_cents=11040,  # 12000 - 960
    )

    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    invoice = summary.invoices[0]
    assert invoice.platform_fee_rate == pytest.approx(0.08)
    assert invoice.platform_fee_cents == 960  # 8% of 12000
    assert invoice.instructor_share_cents == 11040


def test_standard_instructor_12pct_tier_from_db(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    """Standard instructor 12% tier should display correctly when stored in DB."""
    instructor_user, profile, _ = test_instructor

    # Create payment with 12% standard tier
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_standard",
        amount=13440,
        application_fee=1440,  # 12% of 12000
        status="succeeded",
        base_price_cents=12000,
        instructor_tier_pct=Decimal("0.12"),  # Standard rate
        instructor_payout_cents=10560,  # 12000 - 1440
    )

    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    invoice = summary.invoices[0]
    assert invoice.platform_fee_rate == pytest.approx(0.12)
    assert invoice.platform_fee_cents == 1440  # 12% of 12000
    assert invoice.instructor_share_cents == 10560


def test_earnings_accurate_when_credits_applied(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    """Earnings should remain accurate even when platform credits were applied."""
    instructor_user, profile, _ = test_instructor

    # Create payment where student used $20 credit
    # Original: $120 lesson + $14.40 student fee = $134.40
    # After $20 credit: Student pays $114.40, but lesson value unchanged
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_credit_applied",
        amount=11440,  # Student paid after credit
        application_fee=1440,
        status="succeeded",
        # Key: base_price_cents still reflects full lesson value
        base_price_cents=12000,
        instructor_tier_pct=Decimal("0.12"),
        instructor_payout_cents=10560,  # Instructor gets full amount
    )

    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    invoice = summary.invoices[0]
    # Lesson price should still be full value
    assert invoice.lesson_price_cents == 12000
    # Instructor share should be full payout
    assert invoice.instructor_share_cents == 10560


def test_earnings_accurate_after_partial_refund(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple
) -> None:
    """Earnings should reflect original values even after refunds."""
    instructor_user, profile, _ = test_instructor

    # Original payment with full metadata
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_before_refund",
        amount=13440,
        application_fee=1440,
        status="succeeded",
        base_price_cents=12000,
        instructor_tier_pct=Decimal("0.12"),
        instructor_payout_cents=10560,
    )

    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    invoice = summary.invoices[0]
    # Values should remain as originally stored
    assert invoice.lesson_price_cents == 12000
    assert invoice.instructor_share_cents == 10560
    assert invoice.platform_fee_cents == 1440


def test_payment_to_earnings_end_to_end(
    stripe_service: StripeService, test_booking: Booking, test_instructor: tuple, db: Session
) -> None:
    """Integration test: Payment creation to earnings display end-to-end."""
    instructor_user, profile, _ = test_instructor

    # Simulate the flow that happens during booking payment
    # 1. Build charge context (normally done by stripe_service)
    base_price = 12000  # $120/hr * 60min
    tier_pct = Decimal("0.10")  # 10% tier
    platform_fee = int(base_price * tier_pct)  # 1200
    instructor_payout = base_price - platform_fee  # 10800
    student_fee = int(base_price * Decimal("0.12"))  # 1440
    student_pays = base_price + student_fee  # 13440

    # 2. Create payment record with all metadata
    stripe_service.payment_repository.create_payment_record(
        test_booking.id,
        "pi_e2e_test",
        amount=student_pays,
        application_fee=platform_fee + student_fee,  # 2640
        status="succeeded",
        base_price_cents=base_price,
        instructor_tier_pct=tier_pct,
        instructor_payout_cents=instructor_payout,
    )

    # 3. Get earnings summary (as instructor would see it)
    summary = stripe_service.get_instructor_earnings_summary(user=instructor_user)

    # 4. Verify all values display correctly
    assert len(summary.invoices) == 1
    invoice = summary.invoices[0]

    assert invoice.lesson_price_cents == 12000
    assert invoice.platform_fee_rate == pytest.approx(0.10)
    assert invoice.platform_fee_cents == 1200
    assert invoice.instructor_share_cents == 10800
    assert invoice.total_paid_cents == 13440

    # Aggregate totals should also be correct
    assert summary.total_lesson_value == 12000
    assert summary.total_platform_fees == 1200
