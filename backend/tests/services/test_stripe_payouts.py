"""
Payout and earnings summary tests for StripeService.
"""

from datetime import datetime, time, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
import ulid

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


@pytest.mark.xfail(reason="Bug: earnings summary uses default tier, not instructor tier")
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
