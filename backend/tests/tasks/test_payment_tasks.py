"""
Tests for payment processing Celery tasks.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import types
from typing import Any
from unittest.mock import MagicMock, patch

import stripe
from tests.helpers.pricing import cents_from_pct
import ulid

from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services.config_service import DEFAULT_PRICING_CONFIG, ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import ChargeContext, StripeService
from app.tasks.payment_tasks import (
    attempt_authorization_retry,
    attempt_payment_capture,
    capture_completed_lessons,
    check_authorization_health,
    create_new_authorization_and_capture,
    process_scheduled_authorizations,
    retry_failed_authorizations,
)


def _charge_context_from_config(
    *,
    booking_id: str,
    base_price_cents: int,
    credit_cents: int = 0,
    tier_index: int = 0,
) -> ChargeContext:
    tiers = DEFAULT_PRICING_CONFIG.get("instructor_tiers", [])
    tier = tiers[min(tier_index, len(tiers) - 1)] if tiers else {"pct": 0}
    tier_pct = Decimal(str(tier["pct"]))
    student_fee_pct = DEFAULT_PRICING_CONFIG.get("student_fee_pct", 0)
    student_fee_cents = cents_from_pct(base_price_cents, student_fee_pct)
    instructor_commission_cents = cents_from_pct(base_price_cents, tier_pct)
    target_payout = base_price_cents - instructor_commission_cents
    student_pay = max(0, base_price_cents + student_fee_cents - credit_cents)
    application_fee_cents = max(
        0, student_fee_cents + instructor_commission_cents - credit_cents
    )
    top_up_transfer_cents = max(0, target_payout - student_pay)
    return ChargeContext(
        booking_id=booking_id,
        applied_credit_cents=credit_cents,
        base_price_cents=base_price_cents,
        student_fee_cents=student_fee_cents,
        instructor_commission_cents=instructor_commission_cents,
        target_instructor_payout_cents=target_payout,
        student_pay_cents=student_pay,
        application_fee_cents=application_fee_cents,
        top_up_transfer_cents=top_up_transfer_cents,
        instructor_tier_pct=tier_pct,
    )


class TestPaymentTasks:
    """Test suite for payment Celery tasks."""

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_success(self, mock_session_local, mock_stripe_service):
        """Test successful processing of scheduled authorizations."""
        # Setup mock database
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        # Create mock booking that needs authorization
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_test123"
        # Set booking to be exactly 24 hours from now
        from datetime import datetime

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()
        booking.total_price = 100.00

        # Mock query to return the booking
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        mock_stripe_service_instance = mock_stripe_service.return_value
        mock_payment_intent = MagicMock()
        mock_payment_intent.id = "pi_test123"
        mock_stripe_service_instance.create_or_retry_booking_payment_intent.return_value = (
            mock_payment_intent
        )
        mock_stripe_service_instance.build_charge_context.return_value = _charge_context_from_config(
            booking_id=booking.id,
            base_price_cents=10000,
            tier_index=1,
        )

        # Mock repositories
        mock_payment_repo = MagicMock()
        mock_customer = MagicMock()
        mock_customer.stripe_customer_id = "cus_test123"
        mock_payment_repo.get_customer_by_user_id.return_value = mock_customer

        mock_connected_account = MagicMock()
        mock_connected_account.stripe_account_id = "acct_test123"
        mock_payment_repo.get_connected_account_by_instructor_id.return_value = mock_connected_account

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        # Mock instructor profile repository
        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "instructor_profile_id"

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                with patch(
                    "app.repositories.instructor_profile_repository.InstructorProfileRepository"
                ) as mock_instructor_repo_class:
                    mock_instructor_repo = MagicMock()
                    mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
                    mock_instructor_repo_class.return_value = mock_instructor_repo

                    # Execute task
                    result = process_scheduled_authorizations()

        # Verify results
        assert result["success"] == 1
        assert result["failed"] == 0
        assert booking.payment_intent_id == "pi_test123"
        assert booking.payment_status == "authorized"

        # Verify payment event was created
        mock_payment_repo.create_payment_event.assert_called_once()
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "auth_succeeded"

        mock_db.commit.assert_called_once()
        mock_stripe_service_instance.create_or_retry_booking_payment_intent.assert_called_once_with(
            booking_id=booking.id,
            payment_method_id=booking.payment_method_id,
            requested_credit_cents=None,
        )

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_failure(self, mock_session_local, mock_stripe_service):
        """Test handling of authorization failures."""
        # Setup mock database
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        # Create mock booking
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_test123"
        # Set booking to be exactly 24 hours from now
        from datetime import datetime

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()
        booking.total_price = 100.00

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock Stripe service (not used in the actual code)
        mock_stripe_service_instance = mock_stripe_service.return_value
        mock_stripe_service_instance.build_charge_context.return_value = _charge_context_from_config(
            booking_id=booking.id,
            base_price_cents=10000,
        )
        mock_stripe_service_instance.create_or_retry_booking_payment_intent.side_effect = stripe.error.CardError(
            message="Card declined",
            param="payment_method",
            code="card_declined",
            http_body=None,
            http_status=402,
            json_body=None,
            headers=None,
        )

        # Mock repositories
        mock_payment_repo = MagicMock()
        mock_customer = MagicMock()
        mock_customer.stripe_customer_id = "cus_test123"
        mock_payment_repo.get_customer_by_user_id.return_value = mock_customer

        mock_connected_account = MagicMock()
        mock_connected_account.stripe_account_id = "acct_test123"
        mock_payment_repo.get_connected_account_by_instructor_id.return_value = mock_connected_account

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        # Mock instructor profile repository
        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "instructor_profile_id"

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                with patch(
                    "app.repositories.instructor_profile_repository.InstructorProfileRepository"
                ) as mock_instructor_repo_class:
                    mock_instructor_repo = MagicMock()
                    mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
                    mock_instructor_repo_class.return_value = mock_instructor_repo

                    # Execute task
                    result = process_scheduled_authorizations()

        # Verify results
        assert result["success"] == 0
        assert result["failed"] == 1
        assert len(result["failures"]) == 1
        assert result["failures"][0]["error"] == "Card declined"
        assert booking.payment_status == "auth_failed"

        # Verify failure event was created (and allow additional events like T-24 email sent)
        assert mock_payment_repo.create_payment_event.call_count >= 1
        # Ensure at least one event is auth_failed
        event_types = [
            kwargs.get("event_type") for args, kwargs in mock_payment_repo.create_payment_event.call_args_list
        ]
        assert "auth_failed" in event_types

    @patch("app.database.SessionLocal")
    def test_retry_failed_authorizations_success(self, mock_session_local):
        """Test successful retry of failed authorizations."""
        # Setup mock database
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        # Create mock booking with failed auth
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_test123"
        # Set booking to be exactly 20 hours from now (triggers retry)
        from datetime import datetime

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=20)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()
        booking.total_price = 100.00
        booking.student_id = "student_123"
        booking.instructor_id = "instructor_123"

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock payment repository with retry count
        mock_payment_repo = MagicMock()
        mock_event = MagicMock()
        mock_event.event_type = "auth_failed"
        mock_event.event_data = {"used_cents": 0}
        mock_payment_repo.get_payment_events_for_booking.return_value = [mock_event]
        mock_payment_repo.get_applied_credit_cents_for_booking.return_value = 0

        # Mock booking repository
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

        # Mock customer and instructor account
        mock_customer = MagicMock()
        mock_customer.stripe_customer_id = "cus_test123"
        mock_payment_repo.get_customer_by_user_id.return_value = mock_customer

        mock_connected_account = MagicMock()
        mock_connected_account.stripe_account_id = "acct_test123"
        mock_payment_repo.get_connected_account_by_instructor_id.return_value = mock_connected_account

        # Mock instructor profile
        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "instructor_profile_id"

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                with patch(
                    "app.repositories.instructor_profile_repository.InstructorProfileRepository"
                ) as mock_instructor_repo_class:
                    mock_instructor_repo = MagicMock()
                    mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
                    mock_instructor_repo_class.return_value = mock_instructor_repo

                    with patch("app.tasks.payment_tasks.NotificationService") as mock_notification_service:
                        mock_notification_service.return_value = MagicMock()

                        with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service_class:
                            stripe_service_instance = MagicMock()
                            stripe_service_instance.build_charge_context.return_value = (
                                _charge_context_from_config(
                                    booking_id=booking.id,
                                    base_price_cents=10000,
                                    tier_index=1,
                                )
                            )
                            mock_payment_intent = MagicMock()
                            mock_payment_intent.id = "pi_retry123"
                            stripe_service_instance.create_or_retry_booking_payment_intent.return_value = (
                                mock_payment_intent
                            )
                            mock_stripe_service_class.return_value = stripe_service_instance

                            # Execute task
                            result = retry_failed_authorizations()

        # Verify results
        stripe_service_instance = mock_stripe_service_class.return_value
        stripe_service_instance.create_or_retry_booking_payment_intent.assert_called_once_with(
            booking_id=booking.id,
            payment_method_id=booking.payment_method_id,
            requested_credit_cents=None,
        )
        assert result["retried"] == 1
        assert result["success"] == 1
        assert result["failed"] == 0
        assert result["cancelled"] == 0
        assert booking.payment_intent_id == "pi_retry123"
        assert booking.payment_status == "authorized"

    @patch("app.database.SessionLocal")
    def test_retry_failed_authorizations_abandon(self, mock_session_local):
        """Test abandoning bookings after too many retries."""
        # Setup mock database
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        # Create mock booking
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_test123"
        # Set booking to be 5 hours from now (triggers cancellation)
        from datetime import datetime

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=5)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock payment repository with 3 failed attempts
        mock_payment_repo = MagicMock()
        mock_events = [MagicMock(event_type="auth_failed") for _ in range(3)]
        mock_payment_repo.get_payment_events_for_booking.return_value = mock_events

        # Mock booking repository
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                with patch("app.tasks.payment_tasks.NotificationService") as mock_notification_service:
                    notification_instance = MagicMock()
                    mock_notification_service.return_value = notification_instance
                    # Execute task
                    result = retry_failed_authorizations()

        # Verify results
        assert result["retried"] == 0
        assert result["cancelled"] == 1
        assert booking.payment_status == "auth_abandoned"

        # Verify abandonment event was created
        mock_payment_repo.create_payment_event.assert_called_once()
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "auth_abandoned"

        # Verify notification of cancellation due to payment failure was sent (email mocked)
        notification_instance.send_booking_cancelled_payment_failed.assert_called_once_with(booking)

    def test_create_new_authorization_and_capture_application_fee(self):
        """New authorization + capture uses correct application fee scaling."""

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.student_id = "student_789"
        booking.instructor_id = "instructor_789"
        booking.payment_method_id = "pm_test789"
        booking.payment_intent_id = "pi_original"
        booking.total_price = 120.00
        booking.hourly_rate = Decimal("120.00")
        booking.duration_minutes = 60
        booking.location_type = "student_home"
        booking.instructor_service = MagicMock(location_types=None)

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_customer_by_user_id.return_value = MagicMock(stripe_customer_id="cus_789")
        mock_payment_repo.get_connected_account_by_instructor_id.return_value = MagicMock(
            stripe_account_id="acct_789"
        )
        mock_payment_repo.create_payment_event.return_value = None

        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "instructor_profile_789"

        with patch(
            "app.repositories.instructor_profile_repository.InstructorProfileRepository"
        ) as mock_instructor_repo:
            mock_instructor_repo.return_value.get_by_user_id.return_value = mock_instructor_profile

            context = _charge_context_from_config(
                booking_id=booking.id,
                base_price_cents=int(booking.total_price * 100),
            )

            with patch("app.services.stripe_service.stripe") as mock_stripe, \
                patch.object(StripeService, "build_charge_context", return_value=context), \
                patch.object(
                    StripeService,
                    "capture_booking_payment_intent",
                    return_value={
                        "payment_intent": MagicMock(),
                        "amount_received": context.student_pay_cents,
                        "top_up_transfer_cents": context.top_up_transfer_cents,
                    },
                ):
                mock_stripe.PaymentIntent.create.return_value = MagicMock(id="pi_new")

                result = create_new_authorization_and_capture(booking, mock_payment_repo, MagicMock())

                assert result["success"] is True
                _, kwargs = mock_stripe.PaymentIntent.create.call_args

        metadata = kwargs.get("metadata", {})
        base_price_cents = int(metadata.get("base_price_cents", kwargs.get("amount", 0)))
        student_fee_pct = DEFAULT_PRICING_CONFIG["student_fee_pct"]
        student_fee_cents = cents_from_pct(base_price_cents, student_fee_pct)
        commission_cents = int(metadata.get("commission_cents", 0))
        applied_credit_cents = int(metadata.get("applied_credit_cents", "0"))
        expected_fee = max(0, student_fee_cents + commission_cents - applied_credit_cents)
        assert kwargs["application_fee_amount"] == expected_fee

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons(self, mock_session_local, mock_stripe_service):
        """Test capturing payments for completed lessons."""
        # Setup mock database
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        # Create mock completed booking
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.COMPLETED
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_test123"
        booking.completed_at = datetime.now(timezone.utc) - timedelta(hours=25)  # 25 hours ago

        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = [booking]
        mock_db.query.return_value = mock_query

        # Mock Stripe service (not used in the actual code)
        mock_stripe_service_instance = mock_stripe_service.return_value
        mock_captured_intent = MagicMock()
        mock_captured_intent.amount_received = 10000
        mock_stripe_service_instance.capture_booking_payment_intent.return_value = {
            "payment_intent": mock_captured_intent,
            "amount_received": 10000,
        }

        # Mock repositories
        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = [booking]
        mock_booking_repo.get_bookings_for_auto_completion.return_value = []

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                # Execute task
                result = capture_completed_lessons()

        # Verify results
        assert result["captured"] == 1
        assert result["failed"] == 0
        assert booking.payment_status == "captured"

        mock_stripe_service_instance.capture_booking_payment_intent.assert_called_once_with(
            booking_id=booking.id,
            payment_intent_id="pi_test123",
        )

        # Verify capture event was created
        mock_payment_repo.create_payment_event.assert_called_once()
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "payment_captured"

    def test_capture_payment_top_up_idempotent(self):
        """Capture wrapper is used and top-up transfer records once across retries."""

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_topup123"

        events: list[dict[str, Any]] = []

        def record_event(*_, **kwargs):
            events.append(kwargs)

        mock_payment_repo = MagicMock()
        mock_payment_repo.create_payment_event.side_effect = record_event

        stripe_service = MagicMock(spec=StripeService)

        def capture_side_effect(*_, **__):
            has_top_up = any(e.get("event_type") == "top_up_transfer_created" for e in events)
            if not has_top_up:
                record_event(
                    event_type="top_up_transfer_created",
                    event_data={"transfer_id": "tr_topup", "amount_cents": 840},
                )
            payment_intent = MagicMock(amount_received=5960)
            return {
                "payment_intent": payment_intent,
                "amount_received": 5960,
            }

        stripe_service.capture_booking_payment_intent.side_effect = capture_side_effect

        # First capture attempt
        result_first = attempt_payment_capture(
            booking, mock_payment_repo, "instructor_completed", stripe_service
        )
        assert result_first["success"] is True
        assert sum(1 for e in events if e.get("event_type") == "top_up_transfer_created") == 1

        # Reset booking status and retry to confirm idempotency
        booking.payment_status = "authorized"
        result_second = attempt_payment_capture(
            booking, mock_payment_repo, "instructor_completed_retry", stripe_service
        )
        assert result_second["success"] is True
        assert sum(1 for e in events if e.get("event_type") == "top_up_transfer_created") == 1

    @patch("stripe.PaymentIntent.create")
    def test_retry_authorization_reuses_locked_credit_metadata(
        self,
        mock_create,
        db: Any,
    ) -> None:
        """Retry flow should pass requested_credit_cents=None and persist applied credit metadata."""

        stripe_service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
        )
        payment_repo = stripe_service.payment_repository

        student = User(
            id=str(ulid.ULID()),
            email="student_retry@example.com",
            hashed_password="hashed",
            first_name="Retry",
            last_name="Student",
            zip_code="10001",
        )
        instructor_user = User(
            id=str(ulid.ULID()),
            email="instructor_retry@example.com",
            hashed_password="hashed",
            first_name="Retry",
            last_name="Instructor",
            zip_code="10001",
        )
        db.add_all([student, instructor_user])
        db.flush()

        profile = InstructorProfile(
            id=str(ulid.ULID()),
            user_id=instructor_user.id,
            bio="Retry instructor",
            years_experience=5,
        )
        db.add(profile)

        category = ServiceCategory(
            id=str(ulid.ULID()),
            name="Retry Category",
            slug=f"retry-category-{str(ulid.ULID()).lower()}",
            description="Retry category",
        )
        catalog = ServiceCatalog(
            id=str(ulid.ULID()),
            category_id=category.id,
            name="Retry Service",
            slug=f"retry-service-{str(ulid.ULID()).lower()}",
            description="Retry service",
        )
        instructor_service = InstructorService(
            id=str(ulid.ULID()),
            instructor_profile_id=profile.id,
            service_catalog_id=catalog.id,
            hourly_rate=75.0,
            is_active=True,
        )
        db.add_all([category, catalog, instructor_service])

        booking_datetime = datetime.now(timezone.utc) + timedelta(hours=20)
        booking = Booking(
            id=str(ulid.ULID()),
            student_id=student.id,
            instructor_id=instructor_user.id,
            instructor_service_id=instructor_service.id,
            booking_date=booking_datetime.date(),
            start_time=booking_datetime.time(),
            end_time=(booking_datetime + timedelta(hours=1)).time(),
            service_name="Retry Service",
            hourly_rate=75.0,
            total_price=75.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            payment_status="auth_failed",
            payment_method_id="pm_retry",
            payment_intent_id="pi_retry_old",
        )
        db.add(booking)
        db.flush()

        payment_repo.create_customer_record(student.id, "cus_retry")
        payment_repo.create_connected_account_record(
            profile.id, "acct_retry", onboarding_completed=True
        )

        locked_context = _charge_context_from_config(
            booking_id=booking.id,
            base_price_cents=9000,
            credit_cents=12 * 100,
            tier_index=1,
        )

        stripe_service.build_charge_context = MagicMock(return_value=locked_context)

        mock_create.return_value = MagicMock(id="pi_retry_new", status="requires_capture")

        recorded_requested: list[Any] = []
        original_method = stripe_service.create_or_retry_booking_payment_intent

        def _wrapper(self, *, booking_id, payment_method_id=None, requested_credit_cents=None):
            recorded_requested.append(requested_credit_cents)
            return original_method(
                booking_id=booking_id,
                payment_method_id=payment_method_id,
                requested_credit_cents=requested_credit_cents,
            )

        stripe_service.create_or_retry_booking_payment_intent = types.MethodType(
            _wrapper, stripe_service
        )

        result = attempt_authorization_retry(
            booking,
            payment_repo,
            db,
            hours_until_lesson=20,
            stripe_service=stripe_service,
        )

        assert result is True
        assert recorded_requested == [None]
        assert booking.payment_status == "authorized"

        create_kwargs = mock_create.call_args[1]
        assert create_kwargs["metadata"]["applied_credit_cents"] == str(
            locked_context.applied_credit_cents
        )
        assert create_kwargs["amount"] == locked_context.student_pay_cents

    @patch("app.tasks.payment_tasks.get_db")
    def test_check_authorization_health_healthy(self, mock_get_db):
        """Test health check when system is healthy."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock repositories
        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = []  # No overdue bookings

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                # Mock recent event
                mock_event = MagicMock()
                mock_event.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
                mock_query = MagicMock()
                mock_query.filter.return_value.order_by.return_value.first.return_value = mock_event
                mock_db.query.return_value = mock_query

                # Execute task
                result = check_authorization_health()

        # Verify results
        assert result["healthy"] is True
        assert result["overdue_count"] == 0
        assert result["minutes_since_last_auth"] <= 31

    @patch("app.tasks.payment_tasks.get_db")
    def test_check_authorization_health_unhealthy(self, mock_get_db):
        """Test health check when system has issues."""
        # Setup mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock many overdue bookings (health check now counts bookings, not uses count())
        overdue_bookings = [MagicMock(spec=Booking) for _ in range(10)]
        for i, booking in enumerate(overdue_bookings):
            booking.id = f"booking_{i}"
            booking.booking_date = date.today()
            booking.start_time = time(14, 0)
            booking.payment_status = "scheduled"

        # Mock repositories
        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = overdue_bookings

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                # Mock query for last auth event
                mock_query = MagicMock()
                mock_query.filter.return_value.order_by.return_value.first.return_value = None
                mock_db.query.return_value = mock_query

                # Execute task
                result = check_authorization_health()

        # Verify results
        assert result["healthy"] is False
        assert result["overdue_count"] == 10
        assert result["minutes_since_last_auth"] is None
