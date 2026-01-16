from types import SimpleNamespace

from app.services import payment_summary_service as pss


class _Event:
    def __init__(self, event_type, event_data):
        self.event_type = event_type
        self.event_data = event_data


class _PaymentRepoStub:
    def __init__(self, events=None, payment=None, by_amount=None):
        self._events = events or []
        self._payment = payment
        self._by_amount = by_amount

    def get_payment_events_for_booking(self, _booking_id):
        return self._events

    def get_payment_by_intent_id(self, _intent_id):
        return self._payment

    def find_payment_by_booking_and_amount(self, _booking_id, _amount):
        return self._by_amount


class _ReviewTipRepoStub:
    def __init__(self, tip_record=None, raise_error=False):
        self._tip_record = tip_record
        self._raise_error = raise_error

    def get_by_booking_id(self, _booking_id):
        if self._raise_error:
            raise RuntimeError("boom")
        return self._tip_record


def test_to_cents_rounds():
    assert pss._to_cents("1.235") == 124
    assert pss._to_cents(None) == 0


def test_credit_applied_cents_from_events():
    events = [
        _Event("credits_applied", {"applied_cents": 250}),
        _Event("auth_succeeded_credits_only", {"credits_applied_cents": 999}),
    ]
    repo = _PaymentRepoStub(events=events)
    assert pss._credit_applied_cents(repo, "booking") == 250


def test_credit_applied_cents_fallback_auth_only():
    events = [_Event("auth_succeeded_credits_only", {"credits_applied_cents": 400})]
    repo = _PaymentRepoStub(events=events)
    assert pss._credit_applied_cents(repo, "booking") == 400


def test_resolve_tip_info_no_tip():
    repo = _PaymentRepoStub()
    tip_repo = _ReviewTipRepoStub(raise_error=True)
    assert pss._resolve_tip_info(repo, tip_repo, "booking") == (0, 0, None, None)


def test_resolve_tip_info_with_payment():
    tip_record = SimpleNamespace(
        amount_cents=500,
        status="pending",
        processed_at=None,
        stripe_payment_intent_id="pi_123",
    )
    payment = SimpleNamespace(status="succeeded", updated_at=None, created_at=None)
    repo = _PaymentRepoStub(payment=payment)
    tip_repo = _ReviewTipRepoStub(tip_record=tip_record)

    amount, paid, status, _ = pss._resolve_tip_info(repo, tip_repo, "booking")
    assert amount == 500
    assert paid == 500
    assert status == "succeeded"


def test_build_student_payment_summary():
    booking = SimpleNamespace(id="booking", total_price=100.0)
    events = [_Event("credits_applied", {"applied_cents": 100})]
    repo = _PaymentRepoStub(events=events)
    tip_repo = _ReviewTipRepoStub(tip_record=None)

    summary = pss.build_student_payment_summary(
        booking=booking,
        pricing_config={"student_fee_pct": "0.10"},
        payment_repo=repo,
        review_tip_repo=tip_repo,
    )
    assert summary.lesson_amount == 100.0
    assert summary.credit_applied == 1.0
