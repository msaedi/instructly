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
    audit_and_fix_payout_schedules,
    capture_completed_lessons,
    capture_late_cancellation,
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
    instructor_platform_fee_cents = cents_from_pct(base_price_cents, tier_pct)
    target_payout = base_price_cents - instructor_platform_fee_cents
    student_pay = max(0, base_price_cents + student_fee_cents - credit_cents)
    application_fee_cents = max(
        0, student_fee_cents + instructor_platform_fee_cents - credit_cents
    )
    top_up_transfer_cents = max(0, target_payout - student_pay)
    return ChargeContext(
        booking_id=booking_id,
        applied_credit_cents=credit_cents,
        base_price_cents=base_price_cents,
        student_fee_cents=student_fee_cents,
        instructor_platform_fee_cents=instructor_platform_fee_cents,
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
        platform_fee_cents = int(metadata.get("platform_fee_cents", 0))
        # With transfer_data[amount] architecture, we set transfer amount instead of application fee
        expected_transfer_amount = base_price_cents - platform_fee_cents  # instructor payout
        assert kwargs["transfer_data"]["amount"] == expected_transfer_amount
        assert "application_fee_amount" not in kwargs

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

        booking_datetime = datetime.now(timezone.utc) + timedelta(days=1)
        booking_datetime = booking_datetime.replace(hour=15, minute=0, second=0, microsecond=0)
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

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_credits_only(
        self, mock_session_local, mock_stripe_service
    ):
        """Credits-only bookings should skip Stripe and mark authorized."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_credit"
        booking.student_id = "student_credit"
        booking.instructor_id = "instructor_credit"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_customer_by_user_id.return_value = MagicMock()
        mock_payment_repo.get_connected_account_by_instructor_id.return_value = MagicMock(
            stripe_account_id="acct_credit"
        )

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "profile_credit"

        stripe_service_instance = mock_stripe_service.return_value
        stripe_service_instance.build_charge_context.return_value = _charge_context_from_config(
            booking_id=booking.id,
            base_price_cents=10000,
            credit_cents=20000,
        )

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch(
                    "app.repositories.instructor_profile_repository.InstructorProfileRepository"
                ) as mock_instructor_repo_class:
                    mock_instructor_repo = MagicMock()
                    mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
                    mock_instructor_repo_class.return_value = mock_instructor_repo

                    result = process_scheduled_authorizations()

        assert result["success"] == 1
        assert result["failed"] == 0
        assert booking.payment_status == "authorized"
        stripe_service_instance.create_or_retry_booking_payment_intent.assert_not_called()

        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "auth_succeeded_credits_only"

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_skips_outside_window(
        self, mock_session_local, mock_stripe_service
    ):
        """Bookings outside the 23.5-24.5hr window are skipped."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_skip"
        booking.student_id = "student_skip"
        booking.instructor_id = "instructor_skip"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=30)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                result = process_scheduled_authorizations()

        assert result["success"] == 0
        assert result["failed"] == 0
        mock_stripe_service.return_value.build_charge_context.assert_not_called()
        mock_payment_repo.create_payment_event.assert_not_called()

    @patch("app.database.SessionLocal")
    def test_retry_failed_authorizations_t12_sends_warning_and_retries(
        self, mock_session_local
    ):
        """T-12 window sends warning and attempts retry."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_warn"
        booking.student_id = "student_warn"
        booking.instructor_id = "instructor_warn"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=11)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = []

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.NotificationService") as mock_notification:
                    with patch("app.tasks.payment_tasks.StripeService"):
                        with patch(
                            "app.tasks.payment_tasks.attempt_authorization_retry",
                            return_value=True,
                        ) as mock_attempt:
                            result = retry_failed_authorizations()

        assert result["warnings_sent"] == 1
        assert result["retried"] == 1
        assert result["success"] == 1
        mock_attempt.assert_called_once()

        mock_notification.return_value.send_final_payment_warning.assert_called_once()
        event_types = [
            kwargs.get("event_type")
            for args, kwargs in mock_payment_repo.create_payment_event.call_args_list
        ]
        assert "final_warning_sent" in event_types

    @patch("app.database.SessionLocal")
    def test_retry_failed_authorizations_skips_recent_retry_window(
        self, mock_session_local
    ):
        """Recent retry attempts within an hour prevent another retry."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_recent"
        booking.student_id = "student_recent"
        booking.instructor_id = "instructor_recent"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=20)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        recent_event = MagicMock()
        recent_event.event_type = "auth_retry_attempted"
        recent_event.created_at = now - timedelta(minutes=10)

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = [recent_event]

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.NotificationService"):
                    with patch("app.tasks.payment_tasks.StripeService"):
                        with patch(
                            "app.tasks.payment_tasks.attempt_authorization_retry",
                            return_value=True,
                        ) as mock_attempt:
                            result = retry_failed_authorizations()

        assert result["retried"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0
        mock_attempt.assert_not_called()

    def test_attempt_authorization_retry_credits_only(self):
        """Retry flow authorizes when credits cover the full student pay."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.student_id = "student_credit_retry"
        booking.instructor_id = "instructor_credit_retry"
        booking.payment_method_id = "pm_credit_retry"
        booking.payment_intent_id = "pi_credit_retry"

        payment_repo = MagicMock()
        payment_repo.get_customer_by_user_id.return_value = MagicMock()
        payment_repo.get_connected_account_by_instructor_id.return_value = MagicMock(
            stripe_account_id="acct_credit_retry"
        )

        stripe_service = MagicMock(spec=StripeService)
        stripe_service.build_charge_context.return_value = _charge_context_from_config(
            booking_id=booking.id,
            base_price_cents=10000,
            credit_cents=20000,
        )

        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "profile_credit_retry"

        with patch(
            "app.repositories.instructor_profile_repository.InstructorProfileRepository"
        ) as mock_instructor_repo_class:
            mock_instructor_repo = MagicMock()
            mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
            mock_instructor_repo_class.return_value = mock_instructor_repo

            result = attempt_authorization_retry(
                booking,
                payment_repo,
                MagicMock(),
                hours_until_lesson=20,
                stripe_service=stripe_service,
            )

        assert result is True
        assert booking.payment_status == "authorized"
        stripe_service.create_or_retry_booking_payment_intent.assert_not_called()

        event_types = [
            kwargs.get("event_type")
            for args, kwargs in payment_repo.create_payment_event.call_args_list
        ]
        assert "auth_retry_succeeded" in event_types

    def test_attempt_authorization_retry_failure_sets_status(self):
        """Retry failures set auth_retry_failed and record an event."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.student_id = "student_missing"
        booking.instructor_id = "instructor_missing"
        booking.payment_method_id = "pm_missing"

        payment_repo = MagicMock()
        payment_repo.get_customer_by_user_id.return_value = None

        stripe_service = MagicMock(spec=StripeService)

        result = attempt_authorization_retry(
            booking,
            payment_repo,
            MagicMock(),
            hours_until_lesson=20,
            stripe_service=stripe_service,
        )

        assert result is False
        assert booking.payment_status == "auth_retry_failed"
        event_types = [
            kwargs.get("event_type")
            for args, kwargs in payment_repo.create_payment_event.call_args_list
        ]
        assert "auth_retry_failed" in event_types

    def test_attempt_payment_capture_already_captured(self):
        """Already captured payments return success without Stripe call."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "captured"

        payment_repo = MagicMock()
        stripe_service = MagicMock(spec=StripeService)

        result = attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

        assert result["success"] is True
        assert result["already_captured"] is True
        stripe_service.capture_booking_payment_intent.assert_not_called()
        payment_repo.create_payment_event.assert_not_called()

    def test_attempt_payment_capture_expired_auth(self):
        """Expired authorizations return expired status and event."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_expired"

        payment_repo = MagicMock()
        stripe_service = MagicMock(spec=StripeService)
        stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
            message="PaymentIntent has expired",
            param=None,
            code="payment_intent_unexpected_state",
            http_body=None,
            http_status=None,
            json_body=None,
            headers=None,
        )

        result = attempt_payment_capture(
            booking,
            payment_repo,
            "expired_auth",
            stripe_service,
        )

        assert result["success"] is False
        assert result["expired"] is True
        assert booking.payment_status == "auth_expired"
        event_call = payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "capture_failed_expired"

    def test_attempt_payment_capture_card_error(self):
        """Card errors at capture time mark capture_failed."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_card"

        payment_repo = MagicMock()
        stripe_service = MagicMock(spec=StripeService)
        stripe_service.capture_booking_payment_intent.side_effect = stripe.error.CardError(
            message="Insufficient funds",
            param=None,
            code="card_declined",
            http_body=None,
            http_status=402,
            json_body=None,
            headers=None,
        )

        result = attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

        assert result["success"] is False
        assert result["card_error"] is True
        assert booking.payment_status == "capture_failed"
        event_call = payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "capture_failed_card"

    @patch("app.tasks.payment_tasks.attempt_payment_capture", return_value={"success": True})
    @patch("app.tasks.payment_tasks.StudentCreditService")
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_auto_complete(
        self, mock_session_local, mock_credit_service, mock_attempt_capture
    ):
        """Auto-complete past confirmed lessons and capture payment."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.student_id = "student_auto"
        booking.instructor_id = "instructor_auto"
        # Add instructor with timezone for timezone-aware lesson_end calculation
        booking.instructor = MagicMock()
        booking.instructor.timezone = "America/New_York"

        now = datetime.now(timezone.utc)
        # Use 30 hours to account for timezone offset (EST is UTC-5)
        # When we interpret the time as Eastern and convert to UTC, we add 5 hours
        # So 30 hours ago becomes 25 hours ago after timezone conversion
        lesson_end = now - timedelta(hours=30)
        booking.booking_date = lesson_end.date()
        booking.end_time = lesson_end.time()
        booking.payment_intent_id = "pi_test_auto"

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = [booking]
        mock_booking_repo.get_bookings_with_expired_auth.return_value = []

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                    result = capture_completed_lessons()

        assert result["auto_completed"] == 1
        assert result["captured"] == 1
        assert booking.status == BookingStatus.COMPLETED
        assert booking.completed_at is not None
        mock_credit_service.return_value.maybe_issue_milestone_credit.assert_called_once()
        mock_attempt_capture.assert_called_once_with(
            booking, mock_payment_repo, "auto_completed", mock_stripe_service.return_value
        )

        event_types = [
            kwargs.get("event_type")
            for args, kwargs in mock_payment_repo.create_payment_event.call_args_list
        ]
        assert "auto_completed" in event_types

    @patch("app.tasks.payment_tasks.attempt_payment_capture", return_value={"success": True})
    @patch("app.tasks.payment_tasks.StudentCreditService")
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_sets_completed_at_to_lesson_end_time(
        self, mock_session_local, mock_credit_service, mock_attempt_capture
    ):
        """Auto-completed bookings should use lesson end time for completed_at."""
        # Fix: set completed_at to lesson_end for auto-completed lessons.
        from zoneinfo import ZoneInfo

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.student_id = "student_end_time"
        booking.instructor_id = "instructor_end_time"
        # Add instructor with timezone for timezone-aware lesson_end calculation
        booking.instructor = MagicMock()
        booking.instructor.timezone = "America/New_York"

        now = datetime.now(timezone.utc)
        # Use 30 hours to account for timezone offset (EST is UTC-5)
        lesson_end = now - timedelta(hours=30)
        booking.booking_date = lesson_end.date()
        booking.end_time = lesson_end.time()
        booking.payment_intent_id = "pi_test_end_time"

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = [booking]
        mock_booking_repo.get_bookings_with_expired_auth.return_value = []

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    capture_completed_lessons()

        # lesson_end is now calculated using instructor's timezone, then converted to UTC
        instructor_zone = ZoneInfo("America/New_York")
        lesson_end_local = datetime.combine(
            booking.booking_date, booking.end_time, tzinfo=instructor_zone
        )
        expected_completed_at = lesson_end_local.astimezone(timezone.utc)
        assert booking.completed_at == expected_completed_at

    @patch("app.tasks.payment_tasks.create_new_authorization_and_capture", return_value={"success": True})
    @patch("app.tasks.payment_tasks.attempt_payment_capture", return_value={"success": False})
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_expired_auth_reauths(
        self, mock_session_local, mock_attempt_capture, mock_reauth
    ):
        """Expired auths on completed lessons reauthorize and capture."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.COMPLETED
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_expired_reauth"

        now = datetime.now(timezone.utc)
        auth_event = MagicMock()
        auth_event.event_type = "auth_succeeded"
        auth_event.created_at = now - timedelta(days=8)

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = [auth_event]

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = []
        mock_booking_repo.get_bookings_with_expired_auth.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                    result = capture_completed_lessons()

        assert result["expired_handled"] == 1
        assert result["captured"] == 1
        mock_attempt_capture.assert_called_once_with(
            booking, mock_payment_repo, "expired_auth", mock_stripe_service.return_value
        )
        mock_reauth.assert_called_once_with(booking, mock_payment_repo, mock_db)

    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_expired_auth_marks_expired(self, mock_session_local):
        """Expired auths on non-completed lessons are marked expired."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_expired_pending"

        now = datetime.now(timezone.utc)
        auth_event = MagicMock()
        auth_event.event_type = "auth_retry_succeeded"
        auth_event.created_at = now - timedelta(days=8)

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = [auth_event]

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = []
        mock_booking_repo.get_bookings_with_expired_auth.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    result = capture_completed_lessons()

        assert result["expired_handled"] == 1
        assert booking.payment_status == "auth_expired"
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "auth_expired"

    @patch("app.tasks.payment_tasks.get_db")
    def test_capture_late_cancellation_success(self, mock_get_db):
        """Late cancellations capture immediately."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_late"

        now = datetime.now(timezone.utc)
        lesson_time = now + timedelta(hours=6)
        booking.booking_date = lesson_time.date()
        booking.start_time = lesson_time.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_by_id.return_value = booking

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                    stripe_service_instance = mock_stripe_service.return_value
                    captured_intent = MagicMock(amount_received=12000)
                    stripe_service_instance.capture_booking_payment_intent.return_value = (
                        captured_intent
                    )

                    result = capture_late_cancellation(booking.id)

        assert result["success"] is True
        assert booking.payment_status == "captured"
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "late_cancellation_captured"

    @patch("app.tasks.payment_tasks.get_db")
    def test_capture_late_cancellation_not_late(self, mock_get_db):
        """Cancellations with >=12hr notice are not captured."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_not_late"

        now = datetime.now(timezone.utc)
        lesson_time = now + timedelta(hours=14)
        booking.booking_date = lesson_time.date()
        booking.start_time = lesson_time.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_by_id.return_value = booking

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                    result = capture_late_cancellation(booking.id)

        assert result["success"] is False
        assert result["error"] == "Not a late cancellation"
        mock_stripe_service.return_value.capture_booking_payment_intent.assert_not_called()

    @patch("app.tasks.payment_tasks.get_db")
    def test_capture_late_cancellation_no_payment_intent(self, mock_get_db):
        """Late cancellations without a payment intent return an error."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = None

        now = datetime.now(timezone.utc)
        lesson_time = now + timedelta(hours=6)
        booking.booking_date = lesson_time.date()
        booking.start_time = lesson_time.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_by_id.return_value = booking

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                    result = capture_late_cancellation(booking.id)

        assert result["success"] is False
        assert result["error"] == "No payment intent"
        mock_stripe_service.return_value.capture_booking_payment_intent.assert_not_called()

    @patch("app.tasks.payment_tasks.get_db")
    def test_capture_late_cancellation_already_captured(self, mock_get_db):
        """Already captured late cancellations short-circuit."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "captured"
        booking.payment_intent_id = "pi_captured"

        now = datetime.now(timezone.utc)
        lesson_time = now + timedelta(hours=6)
        booking.booking_date = lesson_time.date()
        booking.start_time = lesson_time.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_by_id.return_value = booking

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                    result = capture_late_cancellation(booking.id)

        assert result["success"] is True
        assert result["already_captured"] is True
        mock_stripe_service.return_value.capture_booking_payment_intent.assert_not_called()

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_audit_and_fix_payout_schedules_updates_incorrect(
        self, mock_session_local, mock_stripe_service
    ):
        """Payout schedule audit updates non-weekly Tuesday settings."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        acct_good = MagicMock()
        acct_good.stripe_account_id = "acct_good"
        acct_good.instructor_profile_id = "profile_good"

        acct_bad = MagicMock()
        acct_bad.stripe_account_id = "acct_bad"
        acct_bad.instructor_profile_id = "profile_bad"

        mock_db.query.return_value.all.return_value = [acct_good, acct_bad]

        def _retrieve(account_id: str):
            if account_id == "acct_good":
                return MagicMock(
                    settings={
                        "payouts": {"schedule": {"interval": "weekly", "weekly_anchor": "tuesday"}}
                    }
                )
            return MagicMock(
                settings={
                    "payouts": {"schedule": {"interval": "daily", "weekly_anchor": "monday"}}
                }
            )

        with patch("app.tasks.payment_tasks.stripe.Account.retrieve", side_effect=_retrieve):
            result = audit_and_fix_payout_schedules()

        assert result["checked"] == 2
        assert result["fixed"] == 1
        mock_stripe_service.return_value.set_payout_schedule_for_account.assert_called_once_with(
            instructor_profile_id=acct_bad.instructor_profile_id,
            interval="weekly",
            weekly_anchor="tuesday",
        )

    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_audit_and_fix_payout_schedules_handles_stripe_error(
        self, mock_session_local, mock_stripe_service
    ):
        """Stripe retrieval errors are logged and do not crash the audit."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        acct = MagicMock()
        acct.stripe_account_id = "acct_error"
        acct.instructor_profile_id = "profile_error"

        mock_db.query.return_value.all.return_value = [acct]

        with patch(
            "app.tasks.payment_tasks.stripe.Account.retrieve",
            side_effect=Exception("Stripe down"),
        ):
            result = audit_and_fix_payout_schedules()

        assert result["checked"] == 1
        assert result["fixed"] == 0

    @patch("app.monitoring.prometheus_metrics.prometheus_metrics")
    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_applied_credit_metrics(
        self, mock_session_local, mock_stripe_service, mock_metrics
    ):
        """Applied credits trigger Prometheus metrics for authorization."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_credit_metric"
        booking.student_id = "student_metric"
        booking.instructor_id = "instructor_metric"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_customer_by_user_id.return_value = MagicMock()
        mock_payment_repo.get_connected_account_by_instructor_id.return_value = MagicMock(
            stripe_account_id="acct_metric"
        )

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "profile_metric"

        stripe_service_instance = mock_stripe_service.return_value
        stripe_service_instance.build_charge_context.return_value = _charge_context_from_config(
            booking_id=booking.id,
            base_price_cents=10000,
            credit_cents=2000,
        )
        stripe_service_instance.create_or_retry_booking_payment_intent.return_value = MagicMock(
            id="pi_metric"
        )

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch(
                    "app.repositories.instructor_profile_repository.InstructorProfileRepository"
                ) as mock_instructor_repo_class:
                    mock_instructor_repo = MagicMock()
                    mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
                    mock_instructor_repo_class.return_value = mock_instructor_repo

                    result = process_scheduled_authorizations()

        assert result["success"] == 1
        mock_metrics.inc_credits_applied.assert_called_once_with("authorization")

    @patch("app.database.SessionLocal")
    def test_retry_failed_authorizations_t12_skips_duplicate_warning_and_fails(
        self, mock_session_local
    ):
        """T-12 retry skips warning when already sent and records failure."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_warn_skip"
        booking.student_id = "student_warn_skip"
        booking.instructor_id = "instructor_warn_skip"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=11)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        sent_event = MagicMock()
        sent_event.event_type = "final_warning_sent"
        sent_event.created_at = now - timedelta(hours=1)

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = [sent_event]

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.NotificationService") as mock_notification:
                    with patch("app.tasks.payment_tasks.StripeService"):
                        with patch(
                            "app.tasks.payment_tasks.attempt_authorization_retry",
                            return_value=False,
                        ):
                            result = retry_failed_authorizations()

        assert result["warnings_sent"] == 0
        assert result["failed"] == 1
        assert result["retried"] == 1
        mock_notification.return_value.send_final_payment_warning.assert_not_called()

    def test_attempt_payment_capture_invalid_request_already_captured(self):
        """InvalidRequestError for captured intents records capture_already_done."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_already"

        payment_repo = MagicMock()
        stripe_service = MagicMock(spec=StripeService)
        stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
            message="This PaymentIntent has already been captured",
            param=None,
            code=None,
            http_body=None,
            http_status=None,
            json_body=None,
            headers=None,
        )

        result = attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

        assert result["success"] is True
        assert result["already_captured"] is True
        assert booking.payment_status == "captured"
        event_call = payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "capture_already_done"

    def test_attempt_payment_capture_object_payload_uses_amount(self):
        """Non-dict capture payloads use amount fallback when amount_received is None."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_amount"

        payment_repo = MagicMock()
        stripe_service = MagicMock(spec=StripeService)
        payment_intent = MagicMock(amount_received=None, amount=7890)
        stripe_service.capture_booking_payment_intent.return_value = payment_intent

        result = attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

        assert result["success"] is True
        event_call = payment_repo.create_payment_event.call_args
        assert event_call[1]["event_data"]["amount_captured_cents"] == 7890

    @patch("app.tasks.payment_tasks.StripeService")
    def test_create_new_authorization_and_capture_missing_intent_id(
        self, mock_stripe_service
    ):
        """Missing intent IDs raise and record reauth_and_capture_failed."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_method_id = "pm_missing_intent"
        booking.payment_intent_id = None

        payment_repo = MagicMock()
        stripe_service_instance = mock_stripe_service.return_value
        stripe_service_instance.create_or_retry_booking_payment_intent.return_value = {}

        result = create_new_authorization_and_capture(booking, payment_repo, MagicMock())

        assert result["success"] is False
        event_call = payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "reauth_and_capture_failed"

    @patch("app.tasks.payment_tasks.get_db")
    def test_capture_late_cancellation_booking_not_found(self, mock_get_db):
        """Missing bookings return a not found error."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_by_id.return_value = None

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    result = capture_late_cancellation("missing_booking")

        assert result["success"] is False
        assert result["error"] == "Booking not found"

    @patch("app.tasks.payment_tasks.get_db")
    def test_check_authorization_health_flags_stale_authorizations(self, mock_get_db):
        """Old auth activity marks the system unhealthy."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = []

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                mock_event = MagicMock()
                mock_event.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
                mock_query = MagicMock()
                mock_query.filter.return_value.order_by.return_value.first.return_value = mock_event
                mock_db.query.return_value = mock_query

                result = check_authorization_health()

        assert result["healthy"] is False
        assert result["minutes_since_last_auth"] >= 180

    @patch("app.tasks.payment_tasks.NotificationService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_missing_customer(
        self, mock_session_local, mock_notification_service
    ):
        """Missing Stripe customer marks auth failed and logs a warning email."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_missing_customer"
        booking.student_id = "student_missing_customer"
        booking.instructor_id = "instructor_missing_customer"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_customer_by_user_id.return_value = None
        mock_payment_repo.get_payment_events_for_booking.return_value = []

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                result = process_scheduled_authorizations()

        assert result["failed"] == 1
        assert result["failures"][0]["type"] == "system_error"
        assert booking.payment_status == "auth_failed"
        mock_notification_service.return_value.send_final_payment_warning.assert_called_once()

        event_types = [
            kwargs.get("event_type")
            for args, kwargs in mock_payment_repo.create_payment_event.call_args_list
        ]
        assert "auth_failed" in event_types
        assert "t24_first_failure_email_sent" in event_types

    @patch("app.tasks.payment_tasks.NotificationService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_missing_instructor_profile(
        self, mock_session_local, mock_notification_service
    ):
        """Missing instructor profile triggers auth failure."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_missing_profile"
        booking.student_id = "student_profile"
        booking.instructor_id = "instructor_profile"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_customer_by_user_id.return_value = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = []

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch(
                    "app.repositories.instructor_profile_repository.InstructorProfileRepository"
                ) as mock_instructor_repo_class:
                    mock_instructor_repo = MagicMock()
                    mock_instructor_repo.get_by_user_id.return_value = None
                    mock_instructor_repo_class.return_value = mock_instructor_repo

                    result = process_scheduled_authorizations()

        assert result["failed"] == 1
        assert booking.payment_status == "auth_failed"
        mock_notification_service.return_value.send_final_payment_warning.assert_called_once()

    @patch("app.tasks.payment_tasks.NotificationService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_missing_connected_account(
        self, mock_session_local, mock_notification_service
    ):
        """Missing Stripe connected account triggers auth failure."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_missing_account"
        booking.student_id = "student_account"
        booking.instructor_id = "instructor_account"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_customer_by_user_id.return_value = MagicMock()
        mock_payment_repo.get_connected_account_by_instructor_id.return_value = None
        mock_payment_repo.get_payment_events_for_booking.return_value = []

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "profile_missing_account"

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch(
                    "app.repositories.instructor_profile_repository.InstructorProfileRepository"
                ) as mock_instructor_repo_class:
                    mock_instructor_repo = MagicMock()
                    mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
                    mock_instructor_repo_class.return_value = mock_instructor_repo

                    result = process_scheduled_authorizations()

        assert result["failed"] == 1
        assert booking.payment_status == "auth_failed"
        mock_notification_service.return_value.send_final_payment_warning.assert_called_once()

    @patch("app.tasks.payment_tasks.NotificationService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_t24_email_failure(
        self, mock_session_local, mock_notification_service
    ):
        """T-24 email failures do not crash authorization processing."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_email_fail"
        booking.student_id = "student_email_fail"
        booking.instructor_id = "instructor_email_fail"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_customer_by_user_id.return_value = None
        mock_payment_repo.get_payment_events_for_booking.return_value = []

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        mock_notification_service.return_value.send_final_payment_warning.side_effect = Exception(
            "Email failed"
        )

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                result = process_scheduled_authorizations()

        assert result["failed"] == 1
        event_types = [
            kwargs.get("event_type")
            for args, kwargs in mock_payment_repo.create_payment_event.call_args_list
        ]
        assert "auth_failed" in event_types
        assert "t24_first_failure_email_sent" not in event_types

    @patch("app.monitoring.prometheus_metrics.prometheus_metrics")
    @patch("app.tasks.payment_tasks.StripeService")
    @patch("app.database.SessionLocal")
    def test_process_scheduled_authorizations_metrics_error_is_ignored(
        self, mock_session_local, mock_stripe_service, mock_metrics
    ):
        """Metrics errors should not fail authorization."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "scheduled"
        booking.payment_method_id = "pm_metrics_fail"
        booking.student_id = "student_metrics_fail"
        booking.instructor_id = "instructor_metrics_fail"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=24)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_customer_by_user_id.return_value = MagicMock()
        mock_payment_repo.get_connected_account_by_instructor_id.return_value = MagicMock(
            stripe_account_id="acct_metrics_fail"
        )

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = [booking]

        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "profile_metrics_fail"

        stripe_service_instance = mock_stripe_service.return_value
        stripe_service_instance.build_charge_context.return_value = _charge_context_from_config(
            booking_id=booking.id,
            base_price_cents=10000,
            credit_cents=2000,
        )
        stripe_service_instance.create_or_retry_booking_payment_intent.return_value = MagicMock(
            id="pi_metrics_fail"
        )
        mock_metrics.inc_credits_applied.side_effect = Exception("metrics down")

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch(
                    "app.repositories.instructor_profile_repository.InstructorProfileRepository"
                ) as mock_instructor_repo_class:
                    mock_instructor_repo = MagicMock()
                    mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
                    mock_instructor_repo_class.return_value = mock_instructor_repo

                    result = process_scheduled_authorizations()

        assert result["success"] == 1
        assert booking.payment_status == "authorized"

    @patch("app.database.SessionLocal")
    def test_retry_failed_authorizations_skips_past_lesson(self, mock_session_local):
        """Bookings in the past are skipped."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_past"
        booking.student_id = "student_past"
        booking.instructor_id = "instructor_past"

        now = datetime.now(timezone.utc)
        booking_datetime = now - timedelta(hours=2)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                result = retry_failed_authorizations()

        assert result["retried"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0
        assert result["cancelled"] == 0

    @patch("app.database.SessionLocal")
    def test_retry_failed_authorizations_retry_window_failure(self, mock_session_local):
        """Retry window failures increment failed count."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "auth_failed"
        booking.payment_method_id = "pm_retry_fail"
        booking.student_id = "student_retry_fail"
        booking.instructor_id = "instructor_retry_fail"

        now = datetime.now(timezone.utc)
        booking_datetime = now + timedelta(hours=20)
        booking.booking_date = booking_datetime.date()
        booking.start_time = booking_datetime.time()

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = []

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_retry.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    with patch(
                        "app.tasks.payment_tasks.attempt_authorization_retry",
                        return_value=False,
                    ):
                        result = retry_failed_authorizations()

        assert result["retried"] == 1
        assert result["failed"] == 1

    def test_attempt_authorization_retry_missing_connected_account(self):
        """Missing connected accounts fail retry attempts."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.student_id = "student_no_account"
        booking.instructor_id = "instructor_no_account"
        booking.payment_method_id = "pm_no_account"

        payment_repo = MagicMock()
        payment_repo.get_customer_by_user_id.return_value = MagicMock()
        payment_repo.get_connected_account_by_instructor_id.return_value = None

        stripe_service = MagicMock(spec=StripeService)

        mock_instructor_profile = MagicMock()
        mock_instructor_profile.id = "profile_no_account"

        with patch(
            "app.repositories.instructor_profile_repository.InstructorProfileRepository"
        ) as mock_instructor_repo_class:
            mock_instructor_repo = MagicMock()
            mock_instructor_repo.get_by_user_id.return_value = mock_instructor_profile
            mock_instructor_repo_class.return_value = mock_instructor_repo

            result = attempt_authorization_retry(
                booking,
                payment_repo,
                MagicMock(),
                hours_until_lesson=20,
                stripe_service=stripe_service,
            )

        assert result is False
        assert booking.payment_status == "auth_retry_failed"
        event_types = [
            kwargs.get("event_type")
            for args, kwargs in payment_repo.create_payment_event.call_args_list
        ]
        assert "auth_retry_failed" in event_types

    @patch("app.tasks.payment_tasks.attempt_payment_capture", return_value={"success": False})
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_capture_failure(
        self, mock_session_local, mock_attempt_capture
    ):
        """Failed captures are counted in results."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.COMPLETED
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_failed_capture"
        booking.completed_at = datetime.now(timezone.utc) - timedelta(hours=25)

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = [booking]
        mock_booking_repo.get_bookings_for_auto_completion.return_value = []
        mock_booking_repo.get_bookings_with_expired_auth.return_value = []

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    result = capture_completed_lessons()

        assert result["failed"] == 1
        mock_attempt_capture.assert_called_once()

    @patch("app.tasks.payment_tasks.attempt_payment_capture", return_value={"success": False})
    @patch("app.tasks.payment_tasks.StudentCreditService")
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_auto_complete_capture_failure(
        self, mock_session_local, mock_credit_service, mock_attempt_capture
    ):
        """Auto-complete captures that fail increment failed count."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.student_id = "student_auto_fail"
        booking.instructor_id = "instructor_auto_fail"
        # Add instructor with timezone for timezone-aware lesson_end calculation
        booking.instructor = MagicMock()
        booking.instructor.timezone = "America/New_York"

        now = datetime.now(timezone.utc)
        # Use 30 hours to account for timezone offset (EST is UTC-5)
        lesson_end = now - timedelta(hours=30)
        booking.booking_date = lesson_end.date()
        booking.end_time = lesson_end.time()
        booking.payment_intent_id = "pi_test_auto_fail"

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = [booking]
        mock_booking_repo.get_bookings_with_expired_auth.return_value = []

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    result = capture_completed_lessons()

        assert result["auto_completed"] == 1
        assert result["failed"] == 1
        mock_credit_service.return_value.maybe_issue_milestone_credit.assert_called_once()
        mock_attempt_capture.assert_called_once()

    @patch("app.tasks.payment_tasks.attempt_payment_capture")
    @patch("app.tasks.payment_tasks.StudentCreditService")
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_auto_complete_skips_recent_lessons(
        self, mock_session_local, mock_credit_service, mock_attempt_capture
    ):
        """Lessons ending within 24 hours are not auto-completed."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = "authorized"
        booking.student_id = "student_recent_end"
        booking.instructor_id = "instructor_recent_end"

        now = datetime.now(timezone.utc)
        lesson_end = now - timedelta(hours=1)
        booking.booking_date = lesson_end.date()
        booking.end_time = lesson_end.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = [booking]
        mock_booking_repo.get_bookings_with_expired_auth.return_value = []

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    result = capture_completed_lessons()

        assert result["auto_completed"] == 0
        mock_credit_service.return_value.maybe_issue_milestone_credit.assert_not_called()
        mock_attempt_capture.assert_not_called()

    @patch("app.tasks.payment_tasks.create_new_authorization_and_capture")
    @patch("app.tasks.payment_tasks.attempt_payment_capture", return_value={"success": True})
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_expired_auth_capture_success(
        self, mock_session_local, mock_attempt_capture, mock_reauth
    ):
        """Expired auths that capture successfully do not reauthorize."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.COMPLETED
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_expired_success"

        now = datetime.now(timezone.utc)
        auth_event = MagicMock()
        auth_event.event_type = "auth_succeeded"
        auth_event.created_at = now - timedelta(days=8)

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = [auth_event]

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = []
        mock_booking_repo.get_bookings_with_expired_auth.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    result = capture_completed_lessons()

        assert result["expired_handled"] == 1
        mock_reauth.assert_not_called()

    @patch("app.tasks.payment_tasks.create_new_authorization_and_capture", return_value={"success": False})
    @patch("app.tasks.payment_tasks.attempt_payment_capture", return_value={"success": False})
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_expired_auth_reauth_failure(
        self, mock_session_local, mock_attempt_capture, mock_reauth
    ):
        """Expired auths that fail reauth increment failed count."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.COMPLETED
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_expired_fail"

        now = datetime.now(timezone.utc)
        auth_event = MagicMock()
        auth_event.event_type = "auth_retry_succeeded"
        auth_event.created_at = now - timedelta(days=8)

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = [auth_event]

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = []
        mock_booking_repo.get_bookings_with_expired_auth.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    result = capture_completed_lessons()

        assert result["expired_handled"] == 1
        assert result["failed"] == 1
        mock_reauth.assert_called_once()

    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_expired_auth_not_old(self, mock_session_local):
        """Recent auth events do not trigger expired handling."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.COMPLETED
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_recent_auth"

        now = datetime.now(timezone.utc)
        auth_event = MagicMock()
        auth_event.event_type = "auth_succeeded"
        auth_event.created_at = now - timedelta(days=2)

        mock_payment_repo = MagicMock()
        mock_payment_repo.get_payment_events_for_booking.return_value = [auth_event]

        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = []
        mock_booking_repo.get_bookings_for_auto_completion.return_value = []
        mock_booking_repo.get_bookings_with_expired_auth.return_value = [booking]

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    result = capture_completed_lessons()

        assert result["expired_handled"] == 0

    @patch("app.tasks.payment_tasks.attempt_payment_capture")
    @patch("app.database.SessionLocal")
    def test_capture_completed_lessons_skips_missing_payment_intent_id(
        self, mock_session_local, mock_attempt_capture
    ):
        """Bookings without payment_intent_id should be skipped before capture."""
        # Fix: skip capture when booking.payment_intent_id is missing.
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.status = BookingStatus.COMPLETED
        booking.payment_status = "authorized"
        booking.payment_intent_id = None
        booking.completed_at = datetime.now(timezone.utc) - timedelta(hours=25)

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_capture.return_value = [booking]
        mock_booking_repo.get_bookings_for_auto_completion.return_value = []
        mock_booking_repo.get_bookings_with_expired_auth.return_value = []

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService"):
                    capture_completed_lessons()

        mock_attempt_capture.assert_not_called()

    def test_attempt_payment_capture_invalid_request(self):
        """Invalid request errors record capture_failed."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_invalid"

        payment_repo = MagicMock()
        stripe_service = MagicMock(spec=StripeService)
        stripe_service.capture_booking_payment_intent.side_effect = stripe.error.InvalidRequestError(
            message="Invalid request",
            param=None,
            code="invalid_request",
            http_body=None,
            http_status=None,
            json_body=None,
            headers=None,
        )

        result = attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

        assert result["success"] is False
        event_call = payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "capture_failed"

    def test_attempt_payment_capture_generic_exception(self):
        """Unexpected capture errors are recorded and returned."""
        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_exception"

        payment_repo = MagicMock()
        stripe_service = MagicMock(spec=StripeService)
        stripe_service.capture_booking_payment_intent.side_effect = Exception("capture boom")

        result = attempt_payment_capture(
            booking,
            payment_repo,
            "instructor_completed",
            stripe_service,
        )

        assert result["success"] is False
        event_call = payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "capture_failed"

    @patch("app.tasks.payment_tasks.get_db")
    def test_capture_late_cancellation_invalid_request(self, mock_get_db):
        """Late cancellation invalid request errors log failure."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_late_invalid"

        now = datetime.now(timezone.utc)
        lesson_time = now + timedelta(hours=6)
        booking.booking_date = lesson_time.date()
        booking.start_time = lesson_time.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_by_id.return_value = booking

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                    mock_stripe_service.return_value.capture_booking_payment_intent.side_effect = (
                        stripe.error.InvalidRequestError(
                            message="Invalid state",
                            param=None,
                            code="invalid_state",
                            http_body=None,
                            http_status=None,
                            json_body=None,
                            headers=None,
                        )
                    )
                    result = capture_late_cancellation(booking.id)

        assert result["success"] is False
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "late_cancellation_capture_failed"

    @patch("app.tasks.payment_tasks.get_db")
    def test_capture_late_cancellation_generic_exception(self, mock_get_db):
        """Late cancellation unexpected errors log failure."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        booking = MagicMock(spec=Booking)
        booking.id = str(ulid.ULID())
        booking.payment_status = "authorized"
        booking.payment_intent_id = "pi_late_exception"

        now = datetime.now(timezone.utc)
        lesson_time = now + timedelta(hours=6)
        booking.booking_date = lesson_time.date()
        booking.start_time = lesson_time.time()

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_by_id.return_value = booking

        with patch(
            "app.tasks.payment_tasks.RepositoryFactory.get_payment_repository",
            return_value=mock_payment_repo,
        ):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository",
                return_value=mock_booking_repo,
            ):
                with patch("app.tasks.payment_tasks.StripeService") as mock_stripe_service:
                    mock_stripe_service.return_value.capture_booking_payment_intent.side_effect = (
                        Exception("stripe down")
                    )
                    result = capture_late_cancellation(booking.id)

        assert result["success"] is False
        event_call = mock_payment_repo.create_payment_event.call_args
        assert event_call[1]["event_type"] == "late_cancellation_capture_failed"

    @patch("app.tasks.payment_tasks.get_db")
    def test_check_authorization_health_query_error(self, mock_get_db):
        """Query errors are handled gracefully in health checks."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        mock_payment_repo = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_bookings_for_payment_authorization.return_value = []

        mock_db.query.side_effect = Exception("query failed")

        with patch("app.tasks.payment_tasks.RepositoryFactory.get_payment_repository", return_value=mock_payment_repo):
            with patch(
                "app.tasks.payment_tasks.RepositoryFactory.get_booking_repository", return_value=mock_booking_repo
            ):
                result = check_authorization_health()

        assert result["healthy"] is True
        assert result["minutes_since_last_auth"] is None

    @patch("app.tasks.payment_tasks.get_db")
    def test_check_authorization_health_exception(self, mock_get_db):
        """Health check errors are reported in response."""
        mock_get_db.side_effect = Exception("db unavailable")

        result = check_authorization_health()

        assert result["healthy"] is False
        assert "error" in result
