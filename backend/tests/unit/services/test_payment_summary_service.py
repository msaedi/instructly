from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.services import payment_summary_service as pss


class TestPaymentSummaryService:
    class TestCreditAppliedCents:
        def test_credit_applied_cents_returns_zero_on_repo_exception(self):
            payment_repo = Mock()
            payment_repo.get_payment_events_for_booking.side_effect = Exception("boom")

            result = pss._credit_applied_cents(payment_repo, "booking_1")

            assert result == 0

    class TestResolveTipInfo:
        def test_resolve_tip_info_handles_intent_lookup_exception(self):
            tip_record = SimpleNamespace(
                amount_cents=500,
                status="pending",
                processed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                stripe_payment_intent_id="pi_1",
            )
            review_tip_repo = Mock()
            review_tip_repo.get_by_booking_id.return_value = tip_record

            payment_repo = Mock()
            payment_repo.get_payment_by_intent_id.side_effect = Exception("boom")
            payment_repo.find_payment_by_booking_and_amount.return_value = None

            amount, paid, status, updated = pss._resolve_tip_info(
                payment_repo, review_tip_repo, "booking_1"
            )

            assert amount == 500
            assert paid == 0
            assert status == "pending"
            assert updated == tip_record.processed_at

        def test_resolve_tip_info_handles_find_payment_exception(self):
            tip_record = SimpleNamespace(
                amount_cents=300,
                status="pending",
                processed_at=None,
                stripe_payment_intent_id=None,
            )
            review_tip_repo = Mock()
            review_tip_repo.get_by_booking_id.return_value = tip_record

            payment_repo = Mock()
            payment_repo.find_payment_by_booking_and_amount.side_effect = Exception("boom")

            amount, paid, status, updated = pss._resolve_tip_info(
                payment_repo, review_tip_repo, "booking_1"
            )

            assert amount == 300
            assert paid == 0
            assert status == "pending"
            assert updated is None

        def test_resolve_tip_info_marks_paid_for_success_status(self):
            tip_record = SimpleNamespace(
                amount_cents=700,
                status="pending",
                processed_at=None,
                stripe_payment_intent_id=None,
            )
            review_tip_repo = Mock()
            review_tip_repo.get_by_booking_id.return_value = tip_record

            payment = SimpleNamespace(
                status="processing",
                updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
                created_at=None,
            )
            payment_repo = Mock()
            payment_repo.find_payment_by_booking_and_amount.return_value = payment

            amount, paid, status, updated = pss._resolve_tip_info(
                payment_repo, review_tip_repo, "booking_1"
            )

            assert amount == 700
            assert paid == 700
            assert status == "processing"
            assert updated == payment.updated_at
