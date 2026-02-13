"""Unit tests for StripeService core payment flows."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
import stripe

from app.core.exceptions import ServiceException
from app.models.booking import BookingStatus, PaymentStatus
import app.services.stripe_service as stripe_service
from app.services.stripe_service import ChargeContext, StripeService


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
    service.user_repository = MagicMock()
    service.instructor_repository = MagicMock()
    service.config_service = MagicMock()
    service.pricing_service = MagicMock()
    return service


class _WeirdInt(int):
    def __new__(cls, value: int, display: int) -> "_WeirdInt":
        obj = int.__new__(cls, value)
        obj._display = display
        return obj

    def __str__(self) -> str:
        return str(self._display)


def _make_booking_for_payment(
    *,
    booking_id: str = "booking_1",
    start_utc: object,
    status: str = "PENDING",
) -> SimpleNamespace:
    booking_date = date.today()
    start_time_value = time(10, 0)
    return SimpleNamespace(
        id=booking_id,
        student_id="student_1",
        instructor_id="instructor_1",
        booking_date=booking_date,
        start_time=start_time_value,
        booking_start_utc=start_utc,
        duration_minutes=60,
        status=status,
    )


class TestCustomerManagement:
    def test_create_customer_returns_existing(self):
        service = _make_service()
        existing = SimpleNamespace(id="cust_local", stripe_customer_id="cus_123")
        service.payment_repository.get_customer_by_user_id.return_value = existing

        with patch.object(stripe_service.stripe.Customer, "create") as create_mock:
            result = StripeService.create_customer(
                service, "user_1", "user@example.com", "User One"
            )

        assert result is existing
        create_mock.assert_not_called()

    def test_create_customer_mock_on_auth_error_when_unconfigured(self):
        service = _make_service(stripe_configured=False)
        service.payment_repository.get_customer_by_user_id.return_value = None
        service.payment_repository.create_customer_record.return_value = SimpleNamespace(
            id="cust_db", stripe_customer_id="mock_cust_user_2"
        )

        auth_error = stripe.error.AuthenticationError("No API key provided")
        with patch.object(stripe_service.stripe.Customer, "create", side_effect=auth_error):
            result = StripeService.create_customer(
                service, "user_2", "user2@example.com", "User Two"
            )

        service.payment_repository.create_customer_record.assert_called_once_with(
            user_id="user_2", stripe_customer_id="mock_cust_user_2"
        )
        assert result == service.payment_repository.create_customer_record.return_value

    def test_create_customer_unconfigured_non_auth_error_raises(self):
        service = _make_service(stripe_configured=False)
        service.payment_repository.get_customer_by_user_id.return_value = None

        api_error = stripe.error.APIError("boom")
        with patch.object(stripe_service.stripe.Customer, "create", side_effect=api_error):
            with pytest.raises(ServiceException, match="Failed to create Stripe customer"):
                StripeService.create_customer(
                    service, "user_3", "user3@example.com", "User Three"
                )

    def test_get_or_create_customer_missing_user(self):
        service = _make_service()
        service.payment_repository.get_customer_by_user_id.return_value = None
        service.user_repository.get_by_id.return_value = None

        with pytest.raises(ServiceException, match="not found"):
            StripeService.get_or_create_customer(service, "user_missing")


class TestPaymentIntents:
    def test_create_payment_intent_requires_amount_when_no_context(self):
        service = _make_service()

        with pytest.raises(ServiceException, match="amount_cents is required"):
            StripeService.create_payment_intent(
                service,
                booking_id="booking_1",
                customer_id="cus_1",
                destination_account_id="acct_1",
            )

    def test_create_payment_intent_fallback_mock_when_unconfigured(self):
        service = _make_service(stripe_configured=False)
        service.payment_repository.create_payment_record.return_value = SimpleNamespace(
            id="pay_1", stripe_payment_intent_id="mock_pi_booking_1"
        )

        with patch.object(
            stripe_service.stripe.PaymentIntent, "create", side_effect=Exception("boom")
        ):
            result = StripeService.create_payment_intent(
                service,
                booking_id="booking_1",
                customer_id="cus_1",
                destination_account_id="acct_1",
                amount_cents=5000,
            )

        assert result == service.payment_repository.create_payment_record.return_value
        call_kwargs = service.payment_repository.create_payment_record.call_args.kwargs
        assert call_kwargs["payment_intent_id"] == "mock_pi_booking_1"
        assert call_kwargs["status"] == "requires_payment_method"

    def test_create_payment_intent_platform_fee_rounds_up(self):
        service = _make_service(stripe_configured=False)
        service.platform_fee_percentage = 0.15
        service.payment_repository.create_payment_record.return_value = SimpleNamespace(
            id="pay_2", stripe_payment_intent_id="mock_pi_booking_2"
        )

        with patch.object(
            stripe_service.stripe.PaymentIntent, "create", side_effect=Exception("boom")
        ):
            StripeService.create_payment_intent(
                service,
                booking_id="booking_2",
                customer_id="cus_2",
                destination_account_id="acct_2",
                amount_cents=101,
            )

        call_kwargs = service.payment_repository.create_payment_record.call_args.kwargs
        assert call_kwargs["application_fee"] == 16

    def test_create_and_confirm_manual_authorization_requires_action(self):
        service = _make_service()
        service.payment_repository.upsert_payment_record = None
        service.payment_repository.get_payment_by_intent_id.return_value = None

        pi = SimpleNamespace(id="pi_123", status="requires_action", client_secret="secret_123")

        with patch.object(stripe_service.stripe.PaymentIntent, "create", return_value=pi):
            result = StripeService.create_and_confirm_manual_authorization(
                service,
                booking_id="booking_3",
                customer_id="cus_3",
                destination_account_id="acct_3",
                payment_method_id="pm_1",
                amount_cents=2000,
                idempotency_key="auth_1",
            )

        assert result["requires_action"] is True
        assert result["client_secret"] == "secret_123"
        service.payment_repository.create_payment_record.assert_called_once()

    def test_create_and_confirm_manual_authorization_rounds_fee_up(self):
        service = _make_service()
        service.platform_fee_percentage = 0.15
        service.payment_repository.upsert_payment_record = None
        service.payment_repository.get_payment_by_intent_id.return_value = None

        pi = SimpleNamespace(id="pi_round", status="requires_capture", client_secret=None)

        with patch.object(stripe_service.stripe.PaymentIntent, "create", return_value=pi) as create:
            StripeService.create_and_confirm_manual_authorization(
                service,
                booking_id="booking_round",
                customer_id="cus_round",
                destination_account_id="acct_round",
                payment_method_id="pm_round",
                amount_cents=101,
                idempotency_key="auth_round",
            )

        create_kwargs = create.call_args.kwargs
        assert create_kwargs["transfer_data"]["amount"] == 85

    def test_capture_payment_intent_uses_metadata_fallback(self):
        service = _make_service()
        service.payment_repository.update_payment_status = MagicMock()

        class AttrDict(dict):
            __getattr__ = dict.get

        pi_payload = AttrDict({
            "id": "pi_123",
            "status": "succeeded",
            "amount_received": 4200,
            "charges": {"data": [{"id": "ch_1", "amount": 4200, "transfer": "tr_1"}]},
            "metadata": {"target_instructor_payout_cents": "4200"},
        })

        with patch.object(stripe_service.stripe.PaymentIntent, "capture", return_value=pi_payload):
            with patch.object(
                stripe_service.StripeTransfer, "retrieve", side_effect=Exception("boom")
            ):
                result = StripeService.capture_payment_intent(
                    service, "pi_123", idempotency_key="cap_1"
                )

        assert result["transfer_amount"] == 4200
        assert result["charge_id"] == "ch_1"
        service.payment_repository.update_payment_status.assert_called_once_with(
            "pi_123", "succeeded"
        )

    def test_capture_booking_payment_intent_computes_top_up(self):
        service = _make_service()
        service.stripe_configured = True
        service.capture_payment_intent = MagicMock(
            return_value={"payment_intent": SimpleNamespace(amount=3000, metadata=None)}
        )
        service._top_up_from_pi_metadata = MagicMock(return_value=None)
        service.build_charge_context = MagicMock(
            return_value=ChargeContext(
                booking_id="booking_4",
                applied_credit_cents=0,
                base_price_cents=5000,
                student_fee_cents=0,
                instructor_platform_fee_cents=0,
                target_instructor_payout_cents=5000,
                student_pay_cents=3000,
                application_fee_cents=0,
                top_up_transfer_cents=0,
                instructor_tier_pct=0,
            )
        )
        service.ensure_top_up_transfer = MagicMock()
        service.booking_repository.get_by_id.return_value = SimpleNamespace(
            id="booking_4", instructor_id="inst_user"
        )
        service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="prof_1")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_1")
        )

        with patch.object(
            stripe_service.stripe.PaymentIntent, "retrieve", side_effect=Exception("nope")
        ):
            result = StripeService.capture_booking_payment_intent(
                service,
                booking_id="booking_4",
                payment_intent_id="pi_456",
                idempotency_key="cap_2",
            )

        assert result["top_up_transfer_cents"] == 2000
        service.ensure_top_up_transfer.assert_called_once()


class TestRefundsAndVoids:
    def test_refund_payment_omits_invalid_reason(self):
        service = _make_service()
        refund_obj = SimpleNamespace(id="re_1", status="succeeded", amount=500)

        with patch.object(stripe_service.StripeRefund, "create", return_value=refund_obj) as create:
            result = StripeService.refund_payment(
                service,
                "pi_999",
                amount_cents=500,
                reason="other",
                idempotency_key="refund_1",
            )

        call_kwargs = create.call_args.kwargs
        assert "reason" not in call_kwargs
        assert call_kwargs["idempotency_key"] == "refund_1"
        assert result["refund_id"] == "re_1"

    def test_refund_payment_includes_valid_reason(self):
        service = _make_service()
        refund_obj = SimpleNamespace(id="re_2", status="succeeded", amount=800)

        with patch.object(stripe_service.StripeRefund, "create", return_value=refund_obj) as create:
            StripeService.refund_payment(
                service,
                "pi_100",
                amount_cents=800,
                reason="duplicate",
                idempotency_key="refund_2",
                refund_application_fee=True,
            )

        call_kwargs = create.call_args.kwargs
        assert call_kwargs["reason"] == "duplicate"
        assert call_kwargs["refund_application_fee"] is True
        assert call_kwargs["idempotency_key"] == "refund_2"

    def test_void_or_refund_payment_requires_capture(self):
        service = _make_service()
        service.stripe_configured = True
        service.cancel_payment_intent = MagicMock()
        service.refund_payment = MagicMock()

        with patch.object(
            stripe_service.stripe.PaymentIntent,
            "retrieve",
            return_value=SimpleNamespace(status="requires_capture"),
        ):
            StripeService._void_or_refund_payment(service, "pi_123")

        service.cancel_payment_intent.assert_called_once_with(
            "pi_123", idempotency_key="void_pi_123"
        )
        service.refund_payment.assert_not_called()

    def test_void_or_refund_payment_succeeded(self):
        service = _make_service()
        service.stripe_configured = True
        service.cancel_payment_intent = MagicMock()
        service.refund_payment = MagicMock()

        with patch.object(
            stripe_service.stripe.PaymentIntent,
            "retrieve",
            return_value=SimpleNamespace(status="succeeded"),
        ):
            StripeService._void_or_refund_payment(service, "pi_456")

        service.refund_payment.assert_called_once_with(
            "pi_456",
            reverse_transfer=True,
            refund_application_fee=True,
            idempotency_key="refund_pi_456",
        )
        service.cancel_payment_intent.assert_not_called()


class TestPayoutScheduleAndHistory:
    def test_set_instructor_payout_schedule_with_monthly_anchor(self):
        service = _make_service()
        user = SimpleNamespace(id="user_1")
        profile = SimpleNamespace(id="prof_1")
        service.instructor_repository.get_by_user_id.return_value = profile
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_1")
        )

        with patch.object(
            stripe_service.stripe.Account, "modify", return_value={"id": "acct_1"}
        ) as modify_mock:
            result = StripeService.set_instructor_payout_schedule(
                service,
                user=user,
                monthly_anchor=15,
                interval="monthly",
            )

        modify_kwargs = modify_mock.call_args.kwargs
        assert modify_kwargs["settings"]["payouts"]["schedule"]["monthly_anchor"] == 15
        assert result.account_id == "acct_1"
        assert result.settings["interval"] == "monthly"

    def test_request_instructor_instant_payout_success(self):
        service = _make_service()
        user = SimpleNamespace(id="user_2")
        profile = SimpleNamespace(id="prof_2")
        service.instructor_repository.get_by_user_id.return_value = profile
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_2")
        )

        with patch.object(
            stripe_service.stripe.Payout,
            "create",
            return_value={"id": "po_1", "status": "paid"},
        ):
            result = StripeService.request_instructor_instant_payout(
                service, user=user, amount_cents=2500
            )

        assert result.ok is True
        assert result.payout_id == "po_1"
        assert result.status == "paid"

    def test_get_instructor_payout_history_aggregates_totals(self):
        service = _make_service()
        user = SimpleNamespace(id="user_3")
        profile = SimpleNamespace(id="prof_3")
        service.instructor_repository.get_by_user_id.return_value = profile
        service.payment_repository.get_instructor_payout_history.return_value = [
            SimpleNamespace(
                payout_id="po_paid",
                amount_cents=1000,
                status="paid",
                arrival_date=None,
                failure_code=None,
                failure_message=None,
                created_at=datetime.now(timezone.utc),
            ),
            SimpleNamespace(
                payout_id="po_pending",
                amount_cents=500,
                status="pending",
                arrival_date=None,
                failure_code=None,
                failure_message=None,
                created_at=datetime.now(timezone.utc),
            ),
        ]

        result = StripeService.get_instructor_payout_history(service, user=user, limit=10)

        assert result.total_paid_cents == 1000
        assert result.total_pending_cents == 500
        assert result.payout_count == 2


class TestEarningsSummaryAndExports:
    def test_get_instructor_earnings_summary_rounds_fees_up(self):
        service = _make_service()
        profile = SimpleNamespace(id="prof_fee", is_founding_instructor=False, current_tier_pct=15)
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
            {"student_fee_pct": 0.1, "instructor_tiers": [{"min": 0, "pct": 0.15}]},
            None,
        )

        booking = SimpleNamespace(
            id="booking_fee",
            booking_date=date.today(),
            start_time=time(9, 0),
            service_name="Lesson",
            duration_minutes=60,
            hourly_rate=Decimal("1.01"),
            student=SimpleNamespace(first_name="Alex", last_name="Smith"),
        )
        payment = SimpleNamespace(
            booking=booking,
            amount=101,
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
                result = StripeService.get_instructor_earnings_summary(
                    service, user=SimpleNamespace(id="user_fee")
                )

        invoice = result.invoices[0]
        assert invoice.platform_fee_cents == 16
        assert invoice.student_fee_cents == 10

    def test_get_instructor_earnings_summary_handles_bad_values(self):
        service = _make_service()
        profile = SimpleNamespace(id="prof_bad", is_founding_instructor=False, current_tier_pct="bad")
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

        payment_missing = SimpleNamespace(booking=None)
        booking = SimpleNamespace(
            id="booking_bad",
            booking_date=date.today(),
            start_time=time(9, 0),
            service_name="Lesson",
            duration_minutes=60,
            hourly_rate=object(),
            student=SimpleNamespace(first_name="Pat", last_name=None),
        )
        payment = SimpleNamespace(
            booking=booking,
            amount=0,
            application_fee=0,
            status="failed",
            created_at=datetime.now(timezone.utc),
            base_price_cents=None,
            instructor_tier_pct=None,
            instructor_payout_cents=None,
        )
        service.payment_repository.get_instructor_payment_history.return_value = [
            payment_missing,
            payment,
        ]

        with patch.object(
            stripe_service.RepositoryFactory,
            "create_review_tip_repository",
            return_value=MagicMock(),
        ):
            with patch.object(
                stripe_service,
                "build_student_payment_summary",
                return_value=SimpleNamespace(tip_paid="bad"),
            ):
                result = StripeService.get_instructor_earnings_summary(
                    service, user=SimpleNamespace(id="user_bad")
                )

        assert result.total_lesson_value == 0
        assert result.total_tips == 0
        assert result.invoices[0].student_name == "Pat"

    def test_build_earnings_export_rows_founding_invalid_rate_fallback(self):
        service = _make_service()
        profile = SimpleNamespace(id="prof_export", is_founding_instructor=True, current_tier_pct=None)
        service.instructor_repository.get_by_user_id.return_value = profile
        service.config_service.get_pricing_config.return_value = (
            {"founding_instructor_rate_pct": "bad"},
            None,
        )
        service.payment_repository.get_instructor_earnings_for_export.return_value = [
            {
                "lesson_date": date.today(),
                "student_name": "Student",
                "service_name": "Lesson",
                "duration_minutes": 60,
                "hourly_rate": 100,
                "payment_amount_cents": 10000,
                "application_fee_cents": 1500,
                "status": "succeeded",
                "payment_id": "pay_export",
            }
        ]

        rows = StripeService._build_earnings_export_rows(
            service, instructor_id="prof_export", start_date=None, end_date=None
        )

        assert rows[0]["platform_fee_cents"] == 1500

    def test_build_earnings_export_rows_handles_bad_current_tier_pct(self):
        service = _make_service()
        profile = SimpleNamespace(id="prof_tier", is_founding_instructor=False, current_tier_pct="bad")
        service.instructor_repository.get_by_user_id.return_value = profile
        service.config_service.get_pricing_config.return_value = (
            {"instructor_tiers": []},
            None,
        )
        service.payment_repository.get_instructor_earnings_for_export.return_value = [
            {
                "lesson_date": date.today(),
                "student_name": "Student",
                "service_name": "Lesson",
                "duration_minutes": 60,
                "hourly_rate": 100,
                "payment_amount_cents": 10000,
                "application_fee_cents": 2000,
                "status": "succeeded",
                "payment_id": "pay_export2",
            }
        ]

        rows = StripeService._build_earnings_export_rows(
            service, instructor_id="prof_tier", start_date=None, end_date=None
        )

        assert rows[0]["platform_fee_cents"] >= 0


class TestUserTransactionsAndCredits:
    def test_get_user_transaction_history_instructor_first_name_only(self):
        service = _make_service()
        instructor = SimpleNamespace(first_name="Pat", last_name=None)
        booking = SimpleNamespace(
            id="booking_txn",
            service_name="Lesson",
            instructor=instructor,
            booking_date=date.today(),
            start_time=time(8, 0),
            end_time=time(9, 0),
            duration_minutes=60,
            hourly_rate=50,
        )
        payment = SimpleNamespace(
            id="pay_txn",
            booking=booking,
            status="succeeded",
            created_at=datetime.now(timezone.utc),
        )
        service.payment_repository.get_user_payment_history.return_value = [payment]
        service.config_service.get_pricing_config.return_value = ({}, None)

        summary = SimpleNamespace(
            lesson_amount=50,
            service_fee=5,
            credit_applied=0,
            tip_amount=0,
            tip_paid=0,
            tip_status="none",
            total_paid=55,
        )

        with patch.object(
            stripe_service.RepositoryFactory,
            "create_review_tip_repository",
            return_value=MagicMock(),
        ):
            with patch.object(
                stripe_service, "build_student_payment_summary", return_value=summary
            ):
                result = StripeService.get_user_transaction_history(
                    service, user=SimpleNamespace(id="user_txn"), limit=10, offset=0
                )

        assert result[0].instructor_name == "Pat"

    def test_get_user_credit_balance_handles_expiry_error(self):
        service = _make_service()
        credit_service = MagicMock()
        credit_service.get_available_balance.return_value = 500
        credit_service.get_reserved_balance.return_value = 0
        credit_service.credit_repository.get_available_credits.side_effect = Exception("boom")

        with patch("app.services.credit_service.CreditService", return_value=credit_service):
            result = StripeService.get_user_credit_balance(
                service, user=SimpleNamespace(id="user_credit")
            )

        assert result.expires_at is None


class TestTransfersAndPaymentIntents:
    def test_create_manual_transfer_skips_for_zero_amount(self):
        service = _make_service()
        result = StripeService.create_manual_transfer(
            service,
            booking_id="booking_zero",
            destination_account_id="acct_zero",
            amount_cents=0,
        )

        assert result["skipped"] is True

    def test_create_manual_transfer_success(self):
        service = _make_service()
        transfer_obj = {"id": "tr_123"}

        with patch.object(
            stripe_service.stripe.Transfer, "create", return_value=transfer_obj
        ) as create_mock:
            result = StripeService.create_manual_transfer(
                service,
                booking_id="booking_transfer",
                destination_account_id="acct_transfer",
                amount_cents=1200,
                metadata={"source": "manual"},
            )

        create_kwargs = create_mock.call_args.kwargs
        assert create_kwargs["metadata"]["source"] == "manual"
        assert result["transfer_id"] == "tr_123"

    def test_create_manual_transfer_unexpected_error(self):
        service = _make_service()

        with patch.object(
            stripe_service.stripe.Transfer, "create", side_effect=Exception("boom")
        ):
            with pytest.raises(ServiceException, match="Failed to create transfer"):
                StripeService.create_manual_transfer(
                    service,
                    booking_id="booking_err",
                    destination_account_id="acct_err",
                    amount_cents=500,
                )

    def test_create_referral_bonus_transfer_skip(self):
        service = _make_service()
        result = StripeService.create_referral_bonus_transfer(
            service,
            payout_id="payout_1",
            destination_account_id="acct_bonus",
            amount_cents=0,
            referrer_user_id="ref_1",
            referred_instructor_id="inst_1",
            was_founding_bonus=False,
        )

        assert result["skipped"] is True

    def test_create_referral_bonus_transfer_success(self):
        service = _make_service()
        transfer_obj = {"id": "tr_bonus"}

        with patch.object(
            stripe_service.stripe.Transfer, "create", return_value=transfer_obj
        ) as create_mock:
            result = StripeService.create_referral_bonus_transfer(
                service,
                payout_id="payout_2",
                destination_account_id="acct_bonus",
                amount_cents=7500,
                referrer_user_id="ref_2",
                referred_instructor_id="inst_2",
                was_founding_bonus=True,
            )

        assert result["transfer_id"] == "tr_bonus"
        assert "Founding" in create_mock.call_args.kwargs["description"]

    def test_create_referral_bonus_transfer_unexpected_error(self):
        service = _make_service()

        with patch.object(
            stripe_service.stripe.Transfer, "create", side_effect=Exception("boom")
        ):
            with pytest.raises(ServiceException, match="Failed to create referral bonus transfer"):
                StripeService.create_referral_bonus_transfer(
                    service,
                    payout_id="payout_3",
                    destination_account_id="acct_bonus",
                    amount_cents=5000,
                    referrer_user_id="ref_3",
                    referred_instructor_id="inst_3",
                    was_founding_bonus=False,
                )

    def test_get_payment_intent_capture_details_with_transfer(self):
        service = _make_service()
        pi_payload = {
            "charges": {"data": [{"id": "ch_1", "amount": 5000, "transfer": "tr_1"}]},
            "amount_received": None,
        }

        with patch.object(
            stripe_service.stripe.PaymentIntent, "retrieve", return_value=pi_payload
        ):
            with patch.object(
                stripe_service.StripeTransfer, "retrieve", return_value={"amount": 4200}
            ):
                result = StripeService.get_payment_intent_capture_details(service, "pi_1")

        assert result["charge_id"] == "ch_1"
        assert result["transfer_amount"] == 4200

    def test_get_payment_intent_capture_details_metadata_fallback(self):
        service = _make_service()
        pi_payload = {
            "charges": {"data": [{"id": "ch_2", "amount": None, "transfer": "tr_fail"}]},
            "metadata": {"target_instructor_payout_cents": "3100"},
            "amount": "5000",
        }

        with patch.object(
            stripe_service.stripe.PaymentIntent, "retrieve", return_value=pi_payload
        ):
            with patch.object(
                stripe_service.StripeTransfer, "retrieve", side_effect=Exception("boom")
            ):
                result = StripeService.get_payment_intent_capture_details(service, "pi_2")

        assert result["transfer_amount"] == 3100
        assert result["amount_received"] == 5000

    def test_get_payment_intent_capture_details_stripe_error(self):
        service = _make_service()

        with patch.object(
            stripe_service.stripe.PaymentIntent,
            "retrieve",
            side_effect=stripe.StripeError("boom"),
        ):
            with pytest.raises(ServiceException, match="Failed to retrieve payment intent"):
                StripeService.get_payment_intent_capture_details(service, "pi_fail")

    def test_capture_payment_intent_transfer_amount_from_transfer(self):
        service = _make_service()
        service.payment_repository.update_payment_status = MagicMock()

        class AttrDict(dict):
            __getattr__ = dict.get

        pi_payload = AttrDict({
            "id": "pi_cap",
            "status": "succeeded",
            "charges": {"data": [{"id": "ch_1", "amount": 4200, "transfer": "tr_1"}]},
            "amount_received": 4200,
        })

        with patch.object(
            stripe_service.stripe.PaymentIntent, "capture", return_value=pi_payload
        ):
            with patch.object(
                stripe_service.StripeTransfer, "retrieve", return_value={"amount": 4000}
            ):
                result = StripeService.capture_payment_intent(service, "pi_cap")

        assert result["transfer_amount"] == 4000
        service.payment_repository.update_payment_status.assert_called_once_with(
            "pi_cap", "succeeded"
        )

    def test_reverse_transfer_logs_partial_and_failure(self):
        service = _make_service()
        reversal = {"amount_reversed": 500, "failure_code": "insufficient_funds"}

        with patch.object(
            stripe_service.stripe.Transfer, "create_reversal", return_value=reversal
        ):
            result = StripeService.reverse_transfer(
                service,
                transfer_id="tr_1",
                amount_cents=1000,
                idempotency_key="rev_1",
                reason="dispute",
            )

        assert result["reversal"] == reversal

    def test_reverse_transfer_stripe_error(self):
        service = _make_service()

        with patch.object(
            stripe_service.stripe.Transfer,
            "create_reversal",
            side_effect=stripe.StripeError("boom"),
        ):
            with pytest.raises(ServiceException, match="Failed to reverse transfer"):
                StripeService.reverse_transfer(
                    service,
                    transfer_id="tr_err",
                    amount_cents=100,
                    idempotency_key="rev_err",
                )

    def test_refund_payment_handles_status_update_error(self):
        service = _make_service()
        service.payment_repository.update_payment_status.side_effect = Exception("db down")
        refund_obj = SimpleNamespace(id="re_fail", status="succeeded", amount=500)

        with patch.object(stripe_service.StripeRefund, "create", return_value=refund_obj):
            result = StripeService.refund_payment(
                service,
                "pi_refund",
                amount_cents=500,
                reason="duplicate",
            )

        assert result["refund_id"] == "re_fail"


class TestConnectedAccountEdgeCases:
    def test_create_connected_account_integrity_error_returns_existing(self):
        service = _make_service()
        existing_record = SimpleNamespace(stripe_account_id="acct_existing")
        service.payment_repository.get_connected_account_by_instructor_id.side_effect = [
            None,
            existing_record,
        ]
        integrity_error = IntegrityError("stmt", "params", Exception("orig"))

        with patch.object(
            stripe_service.stripe.Account, "create", side_effect=integrity_error
        ):
            result = StripeService.create_connected_account(
                service, instructor_profile_id="prof_1", email="test@example.com"
            )

        assert result is existing_record

    def test_create_connected_account_unconfigured_integrity_error_returns_existing(self):
        service = _make_service(stripe_configured=False)
        existing_record = SimpleNamespace(stripe_account_id="acct_existing")
        service.payment_repository.get_connected_account_by_instructor_id.side_effect = [
            None,
            None,
            existing_record,
        ]
        integrity_error = IntegrityError("stmt", "params", Exception("orig"))
        service.payment_repository.create_connected_account_record.side_effect = integrity_error

        with patch.object(
            stripe_service.stripe.Account, "create", side_effect=Exception("boom")
        ):
            result = StripeService.create_connected_account(
                service, instructor_profile_id="prof_2", email="test@example.com"
            )

        assert result is existing_record

    def test_check_account_status_collects_requirements(self):
        service = _make_service()
        account_record = SimpleNamespace(
            stripe_account_id="acct_req",
            onboarding_completed=False,
        )
        service.payment_repository.get_connected_account_by_instructor_id.return_value = account_record
        requirements = SimpleNamespace(
            currently_due=["field_a"], past_due=["field_b"], pending_verification=["field_c"]
        )
        stripe_account = SimpleNamespace(
            charges_enabled=True,
            payouts_enabled=True,
            details_submitted=True,
            requirements=requirements,
        )

        with patch.object(
            stripe_service.stripe.Account, "retrieve", return_value=stripe_account
        ):
            result = StripeService.check_account_status(service, "prof_req")

        assert sorted(result["requirements"]) == ["field_a", "field_b", "field_c"]
        service.payment_repository.update_onboarding_status.assert_called_once_with(
            "acct_req", True
        )


class TestCreatePaymentIntentPreviewParity:
    def _make_ctx(self) -> ChargeContext:
        return ChargeContext(
            booking_id="booking_ctx",
            applied_credit_cents=0,
            base_price_cents=1000,
            student_fee_cents=100,
            instructor_platform_fee_cents=150,
            target_instructor_payout_cents=850,
            student_pay_cents=1100,
            application_fee_cents=250,
            top_up_transfer_cents=0,
            instructor_tier_pct=Decimal("0.15"),
        )

    def test_preview_mismatch_student_pay(self):
        service = _make_service()
        ctx = self._make_ctx()
        ctx = ctx.__class__(**{**ctx.__dict__, "student_pay_cents": _WeirdInt(1100, 1200)})

        with patch.object(stripe_service.settings, "environment", "development"):
            with pytest.raises(ServiceException, match="PaymentIntent amount mismatch preview"):
                StripeService.create_payment_intent(
                    service,
                    booking_id="booking_ctx",
                    customer_id="cus_1",
                    destination_account_id="acct_1",
                    charge_context=ctx,
                )

    def test_preview_mismatch_base_price(self):
        service = _make_service()
        ctx = self._make_ctx()
        ctx = ctx.__class__(**{**ctx.__dict__, "base_price_cents": _WeirdInt(1000, 1100)})

        with patch.object(stripe_service.settings, "environment", "development"):
            with pytest.raises(ServiceException, match="PaymentIntent base price mismatch preview"):
                StripeService.create_payment_intent(
                    service,
                    booking_id="booking_ctx",
                    customer_id="cus_1",
                    destination_account_id="acct_1",
                    charge_context=ctx,
                )

    def test_preview_mismatch_student_fee(self):
        service = _make_service()
        ctx = self._make_ctx()
        ctx = ctx.__class__(
            **{**ctx.__dict__, "student_fee_cents": _WeirdInt(100, 120)}
        )

        with patch.object(stripe_service.settings, "environment", "development"):
            with pytest.raises(ServiceException, match="PaymentIntent student fee mismatch preview"):
                StripeService.create_payment_intent(
                    service,
                    booking_id="booking_ctx",
                    customer_id="cus_1",
                    destination_account_id="acct_1",
                    charge_context=ctx,
                )

    def test_preview_mismatch_credit(self):
        service = _make_service()
        ctx = self._make_ctx()
        ctx = ctx.__class__(
            **{**ctx.__dict__, "applied_credit_cents": _WeirdInt(0, 10)}
        )

        with patch.object(stripe_service.settings, "environment", "development"):
            with pytest.raises(ServiceException, match="PaymentIntent credit mismatch preview"):
                StripeService.create_payment_intent(
                    service,
                    booking_id="booking_ctx",
                    customer_id="cus_1",
                    destination_account_id="acct_1",
                    charge_context=ctx,
                )


class TestBookingCheckoutAndProcessing:
    def test_create_booking_checkout_refunds_when_deleted(self):
        service = _make_service()
        booking = SimpleNamespace(
            id="booking_1",
            student_id="student_1",
            status="PENDING",
        )
        service.booking_repository.get_by_id.return_value = booking
        service.booking_repository.get_by_id_for_update.return_value = None
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.process_booking_payment = MagicMock(
            return_value={
                "success": True,
                "payment_intent_id": "pi_1",
                "status": "requires_capture",
                "amount": 10,
                "application_fee": 1,
            }
        )
        service._void_or_refund_payment = MagicMock()
        booking_service = MagicMock()
        booking_service.repository = MagicMock()

        with pytest.raises(Exception):
            StripeService.create_booking_checkout(
                service,
                current_user=SimpleNamespace(id="student_1", is_student=True),
                payload=SimpleNamespace(
                    booking_id="booking_1",
                    payment_method_id=None,
                    save_payment_method=False,
                    requested_credit_cents=None,
                ),
                booking_service=booking_service,
            )

        service._void_or_refund_payment.assert_called_once_with("pi_1")

    def test_create_booking_checkout_refunds_when_cancelled(self):
        service = _make_service()
        booking = SimpleNamespace(
            id="booking_2",
            student_id="student_2",
            status="PENDING",
        )
        cancelled = SimpleNamespace(
            id="booking_2",
            student_id="student_2",
            status=BookingStatus.CANCELLED.value,
        )
        service.booking_repository.get_by_id.return_value = booking
        service.booking_repository.get_by_id_for_update.return_value = cancelled
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.process_booking_payment = MagicMock(
            return_value={
                "success": True,
                "payment_intent_id": "pi_2",
                "status": "requires_capture",
                "amount": 10,
                "application_fee": 1,
            }
        )
        service._void_or_refund_payment = MagicMock()
        booking_service = MagicMock()
        booking_service.repository = MagicMock()

        with pytest.raises(Exception):
            StripeService.create_booking_checkout(
                service,
                current_user=SimpleNamespace(id="student_2", is_student=True),
                payload=SimpleNamespace(
                    booking_id="booking_2",
                    payment_method_id=None,
                    save_payment_method=False,
                    requested_credit_cents=None,
                ),
                booking_service=booking_service,
            )

        service._void_or_refund_payment.assert_called_once_with("pi_2")

    def test_create_booking_checkout_sets_scheduled_status(self):
        service = _make_service()
        booking = SimpleNamespace(
            id="booking_3",
            student_id="student_3",
            status="PENDING",
            confirmed_at=None,
            instructor_service=SimpleNamespace(name="Piano"),
            booking_date=date.today(),
            start_time=time(10, 0),
            instructor_id="inst_3",
        )
        bp_mock = MagicMock()
        service.booking_repository.get_by_id.return_value = booking
        service.booking_repository.get_by_id_for_update.return_value = booking
        service.booking_repository.ensure_payment.return_value = bp_mock
        service.payment_repository.get_payment_by_booking_id.return_value = None
        service.process_booking_payment = MagicMock(
            return_value={
                "success": True,
                "payment_intent_id": "pi_3",
                "status": "scheduled",
                "amount": 10,
                "application_fee": 1,
            }
        )
        booking_service = MagicMock()
        booking_service.repository = MagicMock()
        booking_service.system_message_service = MagicMock()
        booking_service.invalidate_booking_cache = MagicMock()
        booking_service.send_booking_notifications_after_confirmation = MagicMock()

        StripeService.create_booking_checkout(
            service,
            current_user=SimpleNamespace(id="student_3", is_student=True),
            payload=SimpleNamespace(
                booking_id="booking_3",
                payment_method_id=None,
                save_payment_method=False,
                requested_credit_cents=None,
            ),
            booking_service=booking_service,
        )

        assert bp_mock.payment_status == PaymentStatus.SCHEDULED.value
        booking_service.system_message_service.create_booking_created_message.assert_called_once()

    def test_process_booking_payment_credit_only(self):
        service = _make_service()
        booking = _make_booking_for_payment(start_utc="legacy")
        bp_mock = MagicMock()
        service.booking_repository.get_by_id.side_effect = [booking, booking]
        service.booking_repository.ensure_payment.return_value = bp_mock
        service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="prof_1")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_1", onboarding_completed=True)
        )
        service.get_or_create_customer = MagicMock(
            return_value=SimpleNamespace(stripe_customer_id="cus_1")
        )
        service.build_charge_context = MagicMock(
            return_value=ChargeContext(
                booking_id=booking.id,
                applied_credit_cents=5000,
                base_price_cents=5000,
                student_fee_cents=0,
                instructor_platform_fee_cents=0,
                target_instructor_payout_cents=5000,
                student_pay_cents=0,
                application_fee_cents=0,
                top_up_transfer_cents=0,
                instructor_tier_pct=Decimal("0"),
            )
        )

        result = StripeService.process_booking_payment(
            service, booking_id=booking.id, payment_method_id=None, requested_credit_cents=5000
        )

        assert result["status"] == "succeeded"
        assert bp_mock.payment_status == PaymentStatus.AUTHORIZED.value

    def test_process_booking_payment_immediate_auth_card_error(self):
        service = _make_service()
        booking = _make_booking_for_payment(start_utc=datetime.now() + timedelta(hours=1))
        bp_mock = MagicMock()
        bp_mock.auth_failure_count = 0
        service.booking_repository.get_by_id.side_effect = [booking, booking]
        service.booking_repository.ensure_payment.return_value = bp_mock
        service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="prof_2")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_2", onboarding_completed=True)
        )
        service.get_or_create_customer = MagicMock(
            return_value=SimpleNamespace(stripe_customer_id="cus_2")
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
        service.create_payment_intent = MagicMock(
            return_value=SimpleNamespace(
                stripe_payment_intent_id="pi_card",
                amount=5000,
                application_fee=0,
            )
        )

        card_error = stripe.error.CardError(message="declined", param="card", code="card_declined")
        with patch.object(
            stripe_service.stripe.PaymentIntent, "confirm", side_effect=card_error
        ):
            with patch("app.tasks.payment_tasks.check_immediate_auth_timeout") as timeout_task:
                timeout_task.apply_async.side_effect = Exception("boom")
                result = StripeService.process_booking_payment(
                    service,
                    booking_id=booking.id,
                    payment_method_id="pm_1",
                    requested_credit_cents=None,
                )

        assert result["status"] == "auth_failed"
        assert bp_mock.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        assert bp_mock.auth_failure_count == 1

    def test_process_booking_payment_schedules_authorization(self):
        service = _make_service()
        start_dt = datetime.now(timezone.utc) + timedelta(hours=30)
        booking = _make_booking_for_payment(start_utc=start_dt)
        bp_mock = MagicMock()
        service.booking_repository.get_by_id.side_effect = [booking, booking]
        service.booking_repository.ensure_payment.return_value = bp_mock
        service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="prof_3")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_3", onboarding_completed=True)
        )
        service.get_or_create_customer = MagicMock(
            return_value=SimpleNamespace(stripe_customer_id="cus_3")
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
        service.create_payment_intent = MagicMock(
            return_value=SimpleNamespace(
                stripe_payment_intent_id="pi_sched",
                amount=5000,
                application_fee=0,
            )
        )
        service.payment_repository.create_payment_event.side_effect = Exception("boom")

        result = StripeService.process_booking_payment(
            service,
            booking_id=booking.id,
            payment_method_id="pm_sched",
            requested_credit_cents=None,
        )

        assert result["status"] == "scheduled"
        assert bp_mock.payment_status == PaymentStatus.SCHEDULED.value

    def test_create_or_retry_booking_payment_intent_sets_authorized(self):
        service = _make_service()
        booking = SimpleNamespace(
            id="booking_retry",
            student_id="student_4",
            instructor_id="instructor_4",
        )
        bp_mock = MagicMock()
        service.booking_repository.get_by_id.return_value = booking
        service.booking_repository.ensure_payment.return_value = bp_mock
        service.payment_repository.get_customer_by_user_id.return_value = SimpleNamespace(
            stripe_customer_id="cus_retry"
        )
        service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(id="prof_retry")
        service.payment_repository.get_connected_account_by_instructor_id.return_value = (
            SimpleNamespace(stripe_account_id="acct_retry")
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
        service.payment_repository.create_payment_record = MagicMock()

        stripe_intent = SimpleNamespace(id="pi_retry", status="requires_capture")
        with patch.object(
            stripe_service.stripe.PaymentIntent, "create", return_value=stripe_intent
        ):
            result = StripeService.create_or_retry_booking_payment_intent(
                service, booking_id=booking.id
            )

        assert result.id == "pi_retry"
        assert bp_mock.payment_status == PaymentStatus.AUTHORIZED.value


class TestSavePaymentMethodExisting:
    def test_save_payment_method_sets_default_on_existing(self):
        service = _make_service()
        existing = SimpleNamespace(id="pm_db")
        service.payment_repository.get_payment_method_by_stripe_id.return_value = existing

        result = StripeService.save_payment_method(
            service, user_id="user_1", payment_method_id="pm_1", set_as_default=True
        )

        assert result is existing
        service.payment_repository.set_default_payment_method.assert_called_once_with(
            "pm_db", "user_1"
        )


class TestVoidOrRefundAdditionalPaths:
    @pytest.mark.parametrize("payment_intent_id", [None, "local_pi_1"])
    def test_void_or_refund_payment_skips_invalid_ids(self, payment_intent_id):
        service = _make_service()
        service.stripe_configured = True

        StripeService._void_or_refund_payment(service, payment_intent_id)

    def test_void_or_refund_payment_skips_when_unconfigured(self):
        service = _make_service(stripe_configured=False)

        StripeService._void_or_refund_payment(service, "pi_789")

    def test_void_or_refund_payment_other_status(self):
        service = _make_service()
        service.stripe_configured = True
        service.cancel_payment_intent = MagicMock()
        service.refund_payment = MagicMock()

        with patch.object(
            stripe_service.stripe.PaymentIntent,
            "retrieve",
            return_value=SimpleNamespace(status="processing"),
        ):
            StripeService._void_or_refund_payment(service, "pi_processing")

        service.cancel_payment_intent.assert_not_called()
        service.refund_payment.assert_not_called()

    def test_void_or_refund_payment_stripe_error(self):
        service = _make_service()
        service.stripe_configured = True

        with patch.object(
            stripe_service.stripe.PaymentIntent,
            "retrieve",
            side_effect=stripe.StripeError("boom"),
        ):
            StripeService._void_or_refund_payment(service, "pi_error")
