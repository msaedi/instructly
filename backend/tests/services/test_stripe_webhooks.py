"""
Webhook handler tests for StripeService.
"""

from datetime import datetime, time, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
import stripe
import ulid

from app.core.exceptions import ServiceException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import InstructorPayoutEvent
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
        email=f"test_{ulid.ULID()}@example.com",
        hashed_password="hashed",
        first_name="Test",
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
        first_name="Test",
        last_name="Instructor",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(
        id=str(ulid.ULID()),
        user_id=user.id,
        bio="Test instructor",
        years_experience=5,
    )
    db.add(profile)
    db.flush()

    category_ulid = str(ulid.ULID())
    category = (
        db.query(ServiceCategory)
        .filter_by(slug=f"webhook-category-{category_ulid.lower()}")
        .first()
    )
    if not category:
        category = ServiceCategory(
            id=category_ulid,
            name="Webhook Category",
            slug=f"webhook-category-{category_ulid.lower()}",
            description="Webhook category",
        )
        db.add(category)
        db.flush()

    service_ulid = str(ulid.ULID())
    catalog = (
        db.query(ServiceCatalog)
        .filter_by(slug=f"webhook-service-{service_ulid.lower()}")
        .first()
    )
    if not catalog:
        catalog = ServiceCatalog(
            id=service_ulid,
            category_id=category.id,
            name="Webhook Service",
            slug=f"webhook-service-{service_ulid.lower()}",
            description="Webhook service",
        )
        db.add(catalog)
        db.flush()

    service = InstructorService(
        id=str(ulid.ULID()),
        instructor_profile_id=profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=50.00,
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
        start_time=time(14, 0),
        end_time=time(15, 0),
        service_name="Webhook Service",
        hourly_rate=50.00,
        total_price=50.00,
        duration_minutes=60,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.flush()
    return booking


@patch("stripe.Webhook.construct_event")
@patch("app.services.stripe_service.settings")
def test_verify_webhook_signature_valid(
    mock_settings, mock_construct, stripe_service: StripeService
):
    mock_settings.stripe_webhook_secret = "whsec_test_secret"
    mock_construct.return_value = {}

    result = stripe_service.verify_webhook_signature(b"payload", "signature")

    assert result is True
    mock_construct.assert_called_once_with(b"payload", "signature", "whsec_test_secret")


@patch("stripe.Webhook.construct_event")
@patch("app.services.stripe_service.settings")
def test_verify_webhook_signature_invalid(
    mock_settings, mock_construct, stripe_service: StripeService
):
    mock_settings.stripe_webhook_secret = "whsec_test_secret"
    mock_construct.side_effect = stripe.SignatureVerificationError("Invalid", "signature")

    result = stripe_service.verify_webhook_signature(b"payload", "signature")

    assert result is False


@patch("app.services.stripe_service.settings")
def test_handle_webhook_requires_secret(mock_settings, stripe_service: StripeService) -> None:
    mock_settings.stripe_webhook_secret = None

    with pytest.raises(ServiceException, match="Webhook secret not configured"):
        stripe_service.handle_webhook("{}", "sig")


@patch("stripe.Webhook.construct_event")
@patch("app.services.stripe_service.settings")
def test_handle_webhook_invalid_signature(
    mock_settings, mock_construct, stripe_service: StripeService
) -> None:
    mock_settings.stripe_webhook_secret = MagicMock(get_secret_value=lambda: "whsec_test_secret")
    mock_construct.side_effect = stripe.SignatureVerificationError("Invalid", "sig")

    with pytest.raises(ServiceException, match="Invalid webhook signature"):
        stripe_service.handle_webhook("{}", "sig")


@patch("stripe.Webhook.construct_event")
@patch("app.services.stripe_service.settings")
def test_handle_webhook_success(
    mock_settings, mock_construct, stripe_service: StripeService
) -> None:
    mock_settings.stripe_webhook_secret = MagicMock(get_secret_value=lambda: "whsec_test_secret")
    event = {"type": "payment_intent.succeeded"}
    mock_construct.return_value = event

    with patch.object(
        stripe_service,
        "handle_webhook_event",
        return_value={"success": True, "event_type": "payment_intent.succeeded"},
    ) as mock_handle:
        result = stripe_service.handle_webhook("{}", "sig")

    assert result["success"] is True
    assert result["event_type"] == "payment_intent.succeeded"
    mock_handle.assert_called_once_with(event)


@patch("stripe.Webhook.construct_event")
@patch("app.services.stripe_service.settings")
def test_handle_webhook_invalid_payload(
    mock_settings, mock_construct, stripe_service: StripeService
) -> None:
    mock_settings.stripe_webhook_secret = MagicMock(get_secret_value=lambda: "whsec_test_secret")
    mock_construct.side_effect = ValueError("bad payload")

    with pytest.raises(ServiceException, match="Invalid webhook payload"):
        stripe_service.handle_webhook("{}", "sig")


def test_handle_webhook_event_raises_on_handler_error(
    stripe_service: StripeService,
) -> None:
    with patch.object(
        stripe_service,
        "handle_payment_intent_webhook",
        side_effect=Exception("boom"),
    ):
        with pytest.raises(ServiceException, match="Failed to process webhook event"):
            stripe_service.handle_webhook_event({"type": "payment_intent.succeeded"})


@pytest.mark.parametrize(
    ("event_type", "handler_name"),
    [
        ("payment_intent.succeeded", "handle_payment_intent_webhook"),
        ("account.updated", "_handle_account_webhook"),
        ("transfer.paid", "_handle_transfer_webhook"),
        ("charge.refunded", "_handle_charge_webhook"),
        ("payout.paid", "_handle_payout_webhook"),
        ("identity.verification_session.verified", "_handle_identity_webhook"),
    ],
)
def test_handle_webhook_event_dispatches_handlers(
    stripe_service: StripeService, event_type: str, handler_name: str
) -> None:
    with patch.object(stripe_service, handler_name, return_value=True) as mock_handler:
        result = stripe_service.handle_webhook_event({"type": event_type})

    assert result["success"] is True
    assert result["event_type"] == event_type
    mock_handler.assert_called_once()


def test_handle_webhook_event_unknown_type(stripe_service: StripeService) -> None:
    result = stripe_service.handle_webhook_event({"type": "invoice.created"})

    assert result["success"] is True
    assert result["handled"] is False


def test_handle_payment_intent_webhook_success_updates_booking(
    stripe_service: StripeService, test_booking: Booking
) -> None:
    stripe_service.payment_repository.create_payment_record(
        test_booking.id, "pi_webhook", 5000, 750, "requires_payment_method"
    )

    event = {
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_webhook", "status": "succeeded"}},
    }

    success = stripe_service.handle_payment_intent_webhook(event)

    assert success is True
    updated_payment = stripe_service.payment_repository.get_payment_by_intent_id("pi_webhook")
    assert updated_payment.status == "succeeded"
    updated_booking = stripe_service.booking_repository.get_by_id(test_booking.id)
    assert updated_booking.status == BookingStatus.CONFIRMED


def test_handle_payment_intent_webhook_not_found(stripe_service: StripeService) -> None:
    event = {
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_missing", "status": "succeeded"}},
    }

    assert stripe_service.handle_payment_intent_webhook(event) is False


def test_handle_account_webhook_updates_onboarding(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    _, profile, _ = test_instructor
    stripe_service.payment_repository.create_connected_account_record(
        profile.id, "acct_webhook", onboarding_completed=False
    )
    event = {
        "type": "account.updated",
        "data": {"object": {"id": "acct_webhook", "charges_enabled": True, "details_submitted": True}},
    }

    with patch.object(
        stripe_service.payment_repository, "update_onboarding_status"
    ) as mock_update:
        assert stripe_service._handle_account_webhook(event) is True

    mock_update.assert_called_once_with("acct_webhook", True)


def test_handle_account_webhook_deauthorized(stripe_service: StripeService) -> None:
    event = {
        "type": "account.application.deauthorized",
        "data": {"object": {"id": "acct_deauth"}},
    }

    assert stripe_service._handle_account_webhook(event) is True


@pytest.mark.parametrize(
    "event_type",
    ["transfer.created", "transfer.paid", "transfer.failed", "transfer.reversed"],
)
def test_handle_transfer_webhook_events(
    stripe_service: StripeService, event_type: str
) -> None:
    event = {"type": event_type, "data": {"object": {"id": "tr_123", "amount": 100}}}
    assert stripe_service._handle_transfer_webhook(event) is True


def test_handle_transfer_webhook_unhandled(stripe_service: StripeService) -> None:
    event = {"type": "transfer.updated", "data": {"object": {"id": "tr_123"}}}
    assert stripe_service._handle_transfer_webhook(event) is False


def test_handle_charge_refunded_updates_payment_and_credits(
    stripe_service: StripeService, test_booking: Booking
) -> None:
    payment_record = stripe_service.payment_repository.create_payment_record(
        test_booking.id, "pi_refund", 5000, 500, "succeeded"
    )

    event = {
        "type": "charge.refunded",
        "data": {"object": {"id": "ch_refund", "payment_intent": "pi_refund"}},
    }

    with (
        patch.object(stripe_service.payment_repository, "update_payment_status") as mock_update,
        patch.object(
            stripe_service.payment_repository,
            "get_payment_by_intent_id",
            return_value=payment_record,
        ) as mock_get,
        patch("app.services.stripe_service.StudentCreditService") as mock_credit_service,
    ):
        assert stripe_service._handle_charge_webhook(event) is True

    mock_update.assert_called_once_with("pi_refund", "refunded")
    mock_get.assert_called_once_with("pi_refund")
    mock_credit_service.return_value.process_refund_hooks.assert_called_once()


def test_handle_charge_webhook_failed(stripe_service: StripeService) -> None:
    event = {"type": "charge.failed", "data": {"object": {"id": "ch_fail"}}}
    assert stripe_service._handle_charge_webhook(event) is True


def test_payout_persistence_created_paid_failed(db: Session) -> None:
    service = StripeService(
        db,
        config_service=ConfigService(db),
        pricing_service=PricingService(db),
    )

    user = User(
        id=str(ulid.ULID()),
        email=f"ins_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="I",
        last_name="N",
        is_active=True,
        zip_code="10001",
    )
    db.add(user)
    db.flush()
    profile = InstructorProfile(id=str(ulid.ULID()), user_id=user.id)
    db.add(profile)
    db.flush()

    fake_account_id = "acct_123"

    class FakeAcct:
        def __init__(self, instructor_profile_id):
            self.instructor_profile_id = instructor_profile_id

    with patch.object(
        service.payment_repository,
        "get_connected_account_by_stripe_id",
        return_value=FakeAcct(profile.id),
    ):
        created = {
            "type": "payout.created",
            "data": {"object": {"id": "po_1", "amount": 100, "destination": fake_account_id}},
        }
        paid = {
            "type": "payout.paid",
            "data": {"object": {"id": "po_2", "amount": 200, "destination": fake_account_id}},
        }
        failed = {
            "type": "payout.failed",
            "data": {
                "object": {
                    "id": "po_3",
                    "amount": 300,
                    "destination": fake_account_id,
                    "failure_code": "acct",
                    "failure_message": "invalid",
                }
            },
        }

        assert service._handle_payout_webhook(created)
        assert service._handle_payout_webhook(paid)
        assert service._handle_payout_webhook(failed)

    rows = db.query(InstructorPayoutEvent).all()
    ids = {r.payout_id for r in rows}
    assert {"po_1", "po_2", "po_3"}.issubset(ids)


@pytest.mark.xfail(reason="Bug: arrival_date not persisted - see Phase 6 audit")
def test_payout_webhook_stores_arrival_date(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    # FIX: pass arrival_date through to record_payout_event.
    _, profile, _ = test_instructor
    stripe_service.payment_repository.create_connected_account_record(
        profile.id, "acct_arrival", onboarding_completed=True
    )

    arrival = datetime.now(timezone.utc)
    event = {
        "type": "payout.paid",
        "data": {
            "object": {
                "id": "po_arrival",
                "amount": 100,
                "destination": "acct_arrival",
                "arrival_date": arrival,
            }
        },
    }

    assert stripe_service._handle_payout_webhook(event) is True

    rows = stripe_service.payment_repository.get_instructor_payout_history(profile.id, limit=1)
    assert rows[0].arrival_date == arrival


def test_identity_webhook_verified_updates_profile(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, profile, _ = test_instructor
    event = {
        "type": "identity.verification_session.verified",
        "data": {
            "object": {"id": "vs_verified", "status": "verified", "metadata": {"user_id": user.id}}
        },
    }

    assert stripe_service._handle_identity_webhook(event) is True

    updated = stripe_service.instructor_repository.get_by_user_id(user.id)
    assert updated.identity_verified_at is not None
    assert updated.identity_verification_session_id == "vs_verified"


def test_identity_webhook_requires_input_sets_session_id(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, profile, _ = test_instructor
    event = {
        "type": "identity.verification_session.requires_input",
        "data": {
            "object": {"id": "vs_pending", "status": "requires_input", "metadata": {"user_id": user.id}}
        },
    }

    assert stripe_service._handle_identity_webhook(event) is True

    updated = stripe_service.instructor_repository.get_by_user_id(user.id)
    assert updated.identity_verification_session_id == "vs_pending"
    assert updated.identity_verified_at is None


def test_identity_webhook_missing_user_id(stripe_service: StripeService) -> None:
    event = {
        "type": "identity.verification_session.verified",
        "data": {"object": {"id": "vs_ignore", "status": "verified", "metadata": {}}},
    }

    assert stripe_service._handle_identity_webhook(event) is True


def test_identity_webhook_update_failure_returns_false(
    stripe_service: StripeService, test_instructor: tuple
) -> None:
    user, profile, _ = test_instructor
    event = {
        "type": "identity.verification_session.verified",
        "data": {
            "object": {"id": "vs_fail", "status": "verified", "metadata": {"user_id": user.id}}
        },
    }

    with patch.object(stripe_service.instructor_repository, "update", side_effect=Exception("boom")):
        assert stripe_service._handle_identity_webhook(event) is False
