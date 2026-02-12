"""Round 4 coverage tests for StripeService."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ServiceException
from app.models.booking import PaymentStatus
import app.services.stripe_service as stripe_service
from app.services.stripe_service import PRICING_DEFAULTS, ChargeContext, StripeService


@contextmanager
def _noop_txn():
    yield None


def _make_service(*, stripe_configured: bool = True) -> StripeService:
    service = StripeService.__new__(StripeService)
    service.db = MagicMock()
    service.db.commit = MagicMock()
    service.db.rollback = MagicMock()
    service.logger = MagicMock()
    service.cache_service = None
    service.stripe_configured = stripe_configured
    service.platform_fee_percentage = 0.15
    service.payment_repository = MagicMock()
    service.payment_repository.transaction = _noop_txn
    service.booking_repository = MagicMock()
    service.booking_repository.get_transfer_by_booking_id.return_value = None
    service.booking_repository.ensure_dispute.return_value = SimpleNamespace()
    service.booking_repository.ensure_transfer.return_value = SimpleNamespace(
        transfer_reversal_retry_count=0,
        payout_transfer_retry_count=0,
        transfer_retry_count=0,
        refund_retry_count=0,
    )
    service.user_repository = MagicMock()
    service.instructor_repository = MagicMock()
    service.config_service = MagicMock()
    service.pricing_service = MagicMock()
    return service


class AttrDict(dict):
    __getattr__ = dict.get


def _lock_ctx(result: bool):
    @contextmanager
    def _ctx(_booking_id):
        yield result

    return _ctx


class TestCaptureAndDetailsFallbacks:
    def test_capture_payment_intent_metadata_invalid_fallback_amount(self):
        service = _make_service()
        service.payment_repository.update_payment_status = MagicMock()
        pi_payload = AttrDict(
            {
                "id": "pi_cap",
                "status": "succeeded",
                "charges": {"data": [{"id": "ch_1", "amount": None, "transfer": "tr_1"}]},
                "metadata": {"target_instructor_payout_cents": "bad"},
                "amount_received": None,
                "amount": "not-int",
            }
        )

        with patch.object(
            stripe_service.stripe.PaymentIntent, "capture", return_value=pi_payload
        ):
            with patch.object(
                stripe_service.StripeTransfer, "retrieve", side_effect=Exception("boom")
            ):
                result = StripeService.capture_payment_intent(service, "pi_cap")

        assert result["transfer_amount"] is None
        assert result["amount_received"] == "not-int"

    def test_capture_payment_intent_unexpected_error(self):
        service = _make_service()
        with patch.object(
            stripe_service.stripe.PaymentIntent, "capture", side_effect=Exception("boom")
        ):
            with pytest.raises(ServiceException, match="Failed to capture payment"):
                StripeService.capture_payment_intent(service, "pi_fail")

    def test_get_payment_intent_capture_details_metadata_invalid_fallback_amount(self):
        service = _make_service()
        pi_payload = {
            "charges": {"data": [{"id": "ch_2", "amount": None, "transfer": "tr_2"}]},
            "metadata": {"target_instructor_payout_cents": "bad"},
            "amount_received": None,
            "amount": "bad-int",
        }

        with patch.object(
            stripe_service.stripe.PaymentIntent, "retrieve", return_value=pi_payload
        ):
            with patch.object(
                stripe_service.StripeTransfer, "retrieve", side_effect=Exception("boom")
            ):
                result = StripeService.get_payment_intent_capture_details(service, "pi_2")

        assert result["transfer_amount"] is None
        assert result["amount_received"] == "bad-int"

    def test_get_payment_intent_capture_details_unexpected_error(self):
        service = _make_service()
        with patch.object(
            stripe_service.stripe.PaymentIntent, "retrieve", side_effect=Exception("boom")
        ):
            with pytest.raises(ServiceException, match="Failed to retrieve payment intent"):
                StripeService.get_payment_intent_capture_details(service, "pi_err")


class TestEarningsTierFallbacks:
    def test_earnings_export_default_tier_pct_with_percent(self):
        service = _make_service()
        profile = SimpleNamespace(id="prof_1", is_founding_instructor=False, current_tier_pct=15)
        service.instructor_repository.get_by_user_id.return_value = profile
        service.config_service.get_pricing_config.return_value = (
            {"instructor_tiers": []},
            None,
        )
        service.payment_repository.get_instructor_earnings_for_export.return_value = [
            {
                "lesson_date": datetime.now(timezone.utc).date(),
                "student_name": "Student",
                "service_name": "Lesson",
                "duration_minutes": 60,
                "hourly_rate": 100,
                "payment_amount_cents": 10000,
                "application_fee_cents": 1500,
                "status": "succeeded",
                "payment_id": "pay_1",
            }
        ]

        rows = StripeService._build_earnings_export_rows(
            service, instructor_id="prof_1", start_date=None, end_date=None
        )

        assert rows[0]["platform_fee_cents"] >= 0

    def test_earnings_summary_default_tier_when_missing(self):
        service = _make_service()
        profile = SimpleNamespace(id="prof_2", is_founding_instructor=False, current_tier_pct=None)
        service.instructor_repository.get_by_user_id.return_value = profile
        service.get_instructor_earnings = MagicMock(
            return_value={
                "total_earned": 0,
                "total_fees": 0,
                "booking_count": 1,
                "average_earning": 0,
                "period_start": None,
                "period_end": None,
            }
        )
        service.config_service.get_pricing_config.return_value = (
            {"student_fee_pct": 0.1, "instructor_tiers": []},
            None,
        )
        booking = SimpleNamespace(
            id="booking_1",
            booking_date=datetime.now(timezone.utc).date(),
            start_time=datetime.now(timezone.utc).time(),
            service_name="Lesson",
            duration_minutes=60,
            hourly_rate=50,
            student=SimpleNamespace(first_name="Pat", last_name="Lee"),
        )
        payment = SimpleNamespace(
            booking=booking,
            amount=5000,
            application_fee=0,
            status="succeeded",
            created_at=datetime.now(timezone.utc),
            base_price_cents=None,
            instructor_tier_pct=None,
            instructor_payout_cents=None,
        )
        service.payment_repository.get_instructor_payment_history.return_value = [payment]

        with patch.object(
            stripe_service.RepositoryFactory,
            "create_review_tip_repository",
            return_value=MagicMock(),
        ):
            with patch.object(
                stripe_service,
                "build_student_payment_summary",
                return_value=SimpleNamespace(tip_paid=None),
            ):
                summary = StripeService.get_instructor_earnings_summary(
                    service, user=SimpleNamespace(id="user_1")
                )

        default_pct = float(PRICING_DEFAULTS.get("instructor_tiers", [{}])[0].get("pct", 0))
        assert summary.invoices[0].platform_fee_rate == default_pct


class TestCreateRetryAndProcessErrors:
    def test_create_or_retry_payment_intent_raises_when_configured(self):
        service = _make_service(stripe_configured=True)
        booking = SimpleNamespace(
            id="booking_1",
            student_id="student_1",
            instructor_id="instructor_1",
            payment_intent_id=None,
            payment_status=None,
        )
        service.booking_repository.get_by_id.return_value = booking
        service.payment_repository.get_customer_by_user_id.return_value = SimpleNamespace(
            stripe_customer_id="cus_1"
        )
        service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="prof_1")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_1")
        )
        context = ChargeContext(
            booking_id=booking.id,
            applied_credit_cents=0,
            base_price_cents=5000,
            student_fee_cents=0,
            instructor_platform_fee_cents=0,
            target_instructor_payout_cents=5000,
            student_pay_cents=5000,
            application_fee_cents=0,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0"),
        )
        service.build_charge_context = MagicMock(return_value=context)

        with patch.object(
            stripe_service.stripe.PaymentIntent, "create", side_effect=Exception("boom")
        ):
            with pytest.raises(Exception):
                StripeService.create_or_retry_booking_payment_intent(service, booking_id=booking.id)

    def test_process_booking_payment_immediate_auth_generic_error(self):
        service = _make_service()
        start_dt = datetime.now(timezone.utc) + stripe_service.timedelta(hours=1)
        booking = SimpleNamespace(
            id="booking_2",
            student_id="student_2",
            instructor_id="instructor_2",
            booking_date=start_dt.date(),
            start_time=start_dt.time(),
            booking_start_utc=start_dt,
            duration_minutes=60,
            status="PENDING",
            payment_status=None,
            auth_failure_count=0,
            auth_last_error=None,
            auth_scheduled_for=None,
        )
        service.booking_repository.get_by_id.side_effect = [booking, booking]
        service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="prof_2")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_2", onboarding_completed=True)
        )
        service.get_or_create_customer = MagicMock(
            return_value=SimpleNamespace(stripe_customer_id="cus_2")
        )
        service.build_charge_context = MagicMock(
            return_value=ChargeContext(
                booking_id=booking.id,
                applied_credit_cents=0,
                base_price_cents=5000,
                student_fee_cents=0,
                instructor_platform_fee_cents=0,
                target_instructor_payout_cents=5000,
                student_pay_cents=5000,
                application_fee_cents=0,
                top_up_transfer_cents=0,
                instructor_tier_pct=Decimal("0"),
            )
        )
        service.create_payment_intent = MagicMock(
            return_value=SimpleNamespace(
                stripe_payment_intent_id="pi_err",
                amount=5000,
                application_fee=0,
            )
        )

        with patch.object(
            stripe_service.stripe.PaymentIntent, "confirm", side_effect=Exception("boom")
        ):
            result = StripeService.process_booking_payment(
                service,
                booking_id=booking.id,
                payment_method_id="pm_1",
                requested_credit_cents=None,
            )

        assert result["status"] == "auth_failed"
        assert booking.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value


class TestWebhookEdgePaths:
    def test_handle_successful_payment_exception_logged(self):
        service = _make_service()
        service.booking_repository.get_by_id.side_effect = Exception("boom")

        StripeService._handle_successful_payment(
            service, payment_record=SimpleNamespace(booking_id="booking_1")
        )

    def test_handle_account_webhook_updates_onboarding(self):
        service = _make_service()
        event = {
            "type": "account.updated",
            "data": {"object": {"id": "acct_1", "charges_enabled": True, "details_submitted": True}},
        }

        result = StripeService._handle_account_webhook(service, event)

        assert result is True
        service.payment_repository.update_onboarding_status.assert_called_once_with("acct_1", True)

    def test_handle_account_webhook_unknown_event(self):
        service = _make_service()
        event = {"type": "account.unknown", "data": {"object": {"id": "acct_1"}}}
        assert StripeService._handle_account_webhook(service, event) is False

    def test_handle_transfer_webhook_reversed_with_error(self):
        service = _make_service()

        class BadTransfer:
            def get(self, key, default=None):
                if key == "id":
                    return "tr_1"
                if key == "amount":
                    raise Exception("boom")
                return default

        event = {
            "type": "transfer.reversed",
            "data": {"object": BadTransfer()},
        }

        assert StripeService._handle_transfer_webhook(service, event) is True

    def test_handle_charge_webhook_dispute_routes(self):
        service = _make_service()
        service._handle_dispute_created = MagicMock(return_value=True)
        service._handle_dispute_closed = MagicMock(return_value=True)

        created = StripeService._handle_charge_webhook(
            service, {"type": "charge.dispute.created", "data": {"object": {}}}
        )
        closed = StripeService._handle_charge_webhook(
            service, {"type": "charge.dispute.closed", "data": {"object": {}}}
        )

        assert created is True
        assert closed is True

    def test_handle_charge_webhook_refunded_error(self):
        service = _make_service()
        service.payment_repository.update_payment_status.side_effect = Exception("db down")

        event = {
            "type": "charge.refunded",
            "data": {"object": {"id": "ch_1", "payment_intent": "pi_1"}},
        }
        assert StripeService._handle_charge_webhook(service, event) is True

    def test_resolve_payment_intent_from_charge_missing_resource(self):
        service = _make_service()
        service.stripe_configured = True

        with patch.object(stripe_service.stripe, "Charge", None):
            assert StripeService._resolve_payment_intent_id_from_charge(service, "ch_1") is None

    def test_resolve_payment_intent_from_charge_gets_value(self):
        service = _make_service()
        service.stripe_configured = True

        class Charge:
            payment_intent = None

            def get(self, key):
                if key == "payment_intent":
                    return "pi_123"
                return None

        with patch.object(stripe_service.stripe.Charge, "retrieve", return_value=Charge()):
            assert StripeService._resolve_payment_intent_id_from_charge(service, "ch_2") == "pi_123"


class TestDisputeHandlers:
    def test_dispute_created_missing_payment_intent(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value=None)

        event = {"data": {"object": {"id": "dp_1"}}}
        assert StripeService._handle_dispute_created(service, event) is False

    def test_dispute_created_missing_payment_record(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = None

        event = {"data": {"object": {"id": "dp_1"}}}
        assert StripeService._handle_dispute_created(service, event) is False

    def test_dispute_created_missing_booking(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_1"
        )
        service.booking_repository.get_by_id.return_value = None

        event = {"data": {"object": {"id": "dp_1"}}}
        assert StripeService._handle_dispute_created(service, event) is False

    def test_dispute_created_lock_not_acquired(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_1"
        )
        service.booking_repository.get_by_id.return_value = SimpleNamespace(id="booking_1")
        service.booking_repository.get_transfer_by_booking_id.return_value = None

        with patch.object(stripe_service, "booking_lock_sync", _lock_ctx(False)):
            assert StripeService._handle_dispute_created(service, {"data": {"object": {}}}) is False

    def test_dispute_created_reversal_error_and_event_failures(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        payment_record = SimpleNamespace(booking_id="booking_1")
        booking = SimpleNamespace(
            id="booking_1",
            student_id="student_1",
        )
        transfer = SimpleNamespace(
            stripe_transfer_id="tr_1",
            transfer_reversed=False,
            transfer_reversal_retry_count=0,
        )
        service.payment_repository.get_payment_by_intent_id.return_value = payment_record
        service.booking_repository.get_by_id.side_effect = [booking, booking]
        service.booking_repository.get_transfer_by_booking_id.return_value = transfer
        service.booking_repository.ensure_transfer.return_value = transfer
        service.booking_repository.ensure_dispute.return_value = SimpleNamespace()
        service.payment_repository.get_payment_events_for_booking.side_effect = Exception("boom")
        service.payment_repository.create_payment_event.side_effect = [
            Exception("neg"),
            Exception("opened"),
        ]

        credit_service = MagicMock()
        credit_service.get_spent_credits_for_booking.return_value = 500

        with (
            patch.object(service, "reverse_transfer", side_effect=Exception("boom")),
            patch("app.services.credit_service.CreditService", return_value=credit_service),
            patch.object(stripe_service, "booking_lock_sync", _lock_ctx(True)),
        ):
            assert StripeService._handle_dispute_created(service, {"data": {"object": {}}}) is True

        assert transfer.transfer_reversal_failed is True
        assert transfer.transfer_reversal_retry_count == 1

    def test_dispute_created_missing_booking_in_transaction(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_1"
        )
        booking = SimpleNamespace(
            id="booking_1",
            student_id="student_1",
        )
        service.booking_repository.get_transfer_by_booking_id.return_value = None
        service.booking_repository.get_by_id.side_effect = [booking, None]

        credit_service = MagicMock()

        with (
            patch("app.services.credit_service.CreditService", return_value=credit_service),
            patch.object(stripe_service, "booking_lock_sync", _lock_ctx(True)),
        ):
            assert StripeService._handle_dispute_created(service, {"data": {"object": {}}}) is False

    def test_dispute_closed_missing_payment_intent(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value=None)
        event = {"data": {"object": {"id": "dp_1"}}}
        assert StripeService._handle_dispute_closed(service, event) is False

    def test_dispute_closed_missing_payment_record(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = None
        event = {"data": {"object": {"id": "dp_1"}}}
        assert StripeService._handle_dispute_closed(service, event) is False

    def test_dispute_closed_missing_booking(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_1"
        )
        service.booking_repository.get_by_id.return_value = None
        event = {"data": {"object": {"id": "dp_1"}}}
        assert StripeService._handle_dispute_closed(service, event) is False

    def test_dispute_closed_lock_not_acquired(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_1"
        )
        service.booking_repository.get_by_id.return_value = SimpleNamespace(id="booking_1")

        with patch.object(stripe_service, "booking_lock_sync", _lock_ctx(False)):
            assert StripeService._handle_dispute_closed(service, {"data": {"object": {}}}) is False

    def test_dispute_closed_won_handles_bad_amount_and_event_errors(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_1"
        )
        booking = SimpleNamespace(id="booking_1", student_id="student_1")
        service.booking_repository.get_by_id.side_effect = [booking, booking]

        negative_event = SimpleNamespace(event_type="negative_balance_applied", event_data={"amount_cents": "bad"})
        service.payment_repository.get_payment_events_for_booking.return_value = [negative_event]
        service.payment_repository.create_payment_event.side_effect = [
            Exception("neg"),
            Exception("closed"),
        ]

        credit_service = MagicMock()
        credit_service.get_spent_credits_for_booking.return_value = 1000

        with (
            patch("app.services.credit_service.CreditService", return_value=credit_service),
            patch.object(stripe_service, "booking_lock_sync", _lock_ctx(True)),
        ):
            event = {"data": {"object": {"id": "dp_1", "status": "won"}}}
            assert StripeService._handle_dispute_closed(service, event) is True

        assert booking.settlement_outcome == "dispute_won"

    def test_dispute_closed_lost_handles_event_errors(self):
        service = _make_service()
        service._resolve_payment_intent_id_from_charge = MagicMock(return_value="pi_1")
        service.payment_repository.get_payment_by_intent_id.return_value = SimpleNamespace(
            booking_id="booking_1"
        )
        booking = SimpleNamespace(id="booking_1", student_id="student_1")
        service.booking_repository.get_by_id.side_effect = [booking, booking]
        service.payment_repository.get_payment_events_for_booking.side_effect = Exception("boom")
        service.payment_repository.create_payment_event.side_effect = [
            Exception("neg"),
            Exception("closed"),
        ]

        credit_service = MagicMock()
        credit_service.get_spent_credits_for_booking.return_value = 300

        user_repo = MagicMock()
        user_repo.get_by_id.return_value = SimpleNamespace(account_restricted=False)

        with (
            patch("app.services.credit_service.CreditService", return_value=credit_service),
            patch.object(stripe_service.RepositoryFactory, "create_base_repository", return_value=user_repo),
            patch.object(stripe_service, "booking_lock_sync", _lock_ctx(True)),
        ):
            event = {"data": {"object": {"id": "dp_1", "status": "lost"}}}
            assert StripeService._handle_dispute_closed(service, event) is True

        assert booking.settlement_outcome == "student_wins_dispute_full_refund"


class TestPayoutAndIdentityErrors:
    def test_payout_created_persist_error_logged(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_stripe_id.side_effect = Exception("boom")

        event = {
            "type": "payout.created",
            "data": {"object": {"id": "po_1", "amount": 100, "status": "created", "destination": "acct"}},
        }
        assert StripeService._handle_payout_webhook(service, event) is True

    def test_payout_paid_notification_error(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_stripe_id.return_value = SimpleNamespace(
            instructor_profile_id="prof_1"
        )
        service.instructor_repository.get_by_id_join_user.return_value = SimpleNamespace(
            user_id="user_1"
        )

        event = {
            "type": "payout.paid",
            "data": {"object": {"id": "po_2", "amount": 100, "status": "paid", "destination": "acct"}},
        }

        with patch(
            "app.services.notification_service.NotificationService",
            side_effect=Exception("boom"),
        ):
            assert StripeService._handle_payout_webhook(service, event) is True

    def test_payout_paid_persist_error(self):
        service = _make_service()
        service.payment_repository.get_connected_account_by_stripe_id.return_value = SimpleNamespace(
            instructor_profile_id="prof_2"
        )
        service.payment_repository.record_payout_event.side_effect = Exception("boom")

        event = {
            "type": "payout.paid",
            "data": {"object": {"id": "po_3", "amount": 100, "status": "paid", "destination": "acct"}},
        }
        assert StripeService._handle_payout_webhook(service, event) is True

    def test_payout_webhook_outer_error(self):
        service = _make_service()
        event = {"type": "payout.created", "data": None}
        assert StripeService._handle_payout_webhook(service, event) is False

    def test_identity_webhook_outer_error(self):
        service = _make_service()
        service.instructor_repository.get_by_user_id.side_effect = Exception("boom")
        event = {
            "type": "identity.verification_session.verified",
            "data": {"object": {"id": "vs_1", "status": "verified", "metadata": {"user_id": "u1"}}},
        }

        assert StripeService._handle_identity_webhook(service, event) is False


class TestRefundAndTransferErrors:
    def test_reverse_transfer_generic_error(self):
        service = _make_service()

        with patch.object(
            stripe_service.stripe.Transfer, "create_reversal", side_effect=Exception("boom")
        ):
            with pytest.raises(ServiceException, match="Failed to reverse transfer"):
                StripeService.reverse_transfer(service, transfer_id="tr_1")

    def test_void_or_refund_payment_logs_generic_error(self):
        service = _make_service()
        service.stripe_configured = True

        with patch.object(
            stripe_service.stripe.PaymentIntent, "retrieve", side_effect=Exception("boom")
        ):
            StripeService._void_or_refund_payment(service, "pi_1")
