"""
Additional webhook tests: charge.refunded, transfer.reversed, payout.* dispatch.
"""

from unittest.mock import patch

from app.services.stripe_service import StripeService


def test_charge_refunded_updates_status(db):
    service = StripeService(db)
    event = {
        "type": "charge.refunded",
        "data": {"object": {"id": "ch_x", "payment_intent": "pi_123"}},
    }

    with patch.object(service.payment_repository, "update_payment_status") as mock_update:
        service._handle_charge_webhook(event)
        mock_update.assert_called_once_with("pi_123", "refunded")


def test_transfer_reversed_logs(db, caplog):
    service = StripeService(db)
    event = {"type": "transfer.reversed", "data": {"object": {"id": "tr_123", "amount": 100}}}

    assert service._handle_transfer_webhook(event) is True


def test_payout_events_dispatch(db):
    service = StripeService(db)
    created = {"type": "payout.created", "data": {"object": {"id": "po_1", "amount": 100}}}
    paid = {"type": "payout.paid", "data": {"object": {"id": "po_2", "amount": 200}}}
    failed = {
        "type": "payout.failed",
        "data": {"object": {"id": "po_3", "amount": 300, "failure_code": "acct", "failure_message": "x"}},
    }

    assert service._handle_payout_webhook(created) is True
    assert service._handle_payout_webhook(paid) is True
    assert service._handle_payout_webhook(failed) is True
