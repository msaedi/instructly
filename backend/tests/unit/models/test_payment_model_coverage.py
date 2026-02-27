"""
Coverage tests for app/models/payment.py — targeting uncovered lines:
  L319: is_expired when status == "reserved" → False
  L321: is_expired when status == "frozen" → False
  L323: is_expired when status == "revoked" → False
  L325: is_expired when status == "expired" → True

Bug hunts:
  - Status transitions
  - Timezone-aware vs naive datetime comparison
  - Edge cases in is_expired and is_available
"""

from datetime import datetime, timedelta, timezone

from app.models.payment import PlatformCredit


def _make_credit(**kwargs) -> PlatformCredit:
    """Create a PlatformCredit instance with sensible defaults.

    Uses SQLAlchemy's declarative __init__ so that _sa_instance_state
    is properly initialised and instrumented attribute descriptors work.
    """
    defaults = {
        "user_id": "user_01ABC",
        "amount_cents": 1000,
        "reason": "test credit",
        "status": "available",
        "expires_at": None,
        "source_type": "manual",
    }
    defaults.update(kwargs)
    return PlatformCredit(**defaults)


# ──────────────────────────────────────────────────────────────
# is_expired property
# ──────────────────────────────────────────────────────────────

class TestIsExpired:
    def test_reserved_never_expired(self):
        """L319: status == 'reserved' → False, regardless of expires_at."""
        credit = _make_credit(
            status="reserved",
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),  # Past date
        )
        assert credit.is_expired is False

    def test_frozen_never_expired(self):
        """L321: status == 'frozen' → False."""
        credit = _make_credit(
            status="frozen",
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        assert credit.is_expired is False

    def test_revoked_never_expired(self):
        """L323: status == 'revoked' → False."""
        credit = _make_credit(
            status="revoked",
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        assert credit.is_expired is False

    def test_expired_status_is_expired(self):
        """L325: status == 'expired' → True."""
        credit = _make_credit(status="expired")
        assert credit.is_expired is True

    def test_available_no_expires_at(self):
        """Available with no expiry → not expired."""
        credit = _make_credit(status="available", expires_at=None)
        assert credit.is_expired is False

    def test_available_future_expires(self):
        """Available with future expiry → not expired."""
        credit = _make_credit(
            status="available",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        assert credit.is_expired is False

    def test_available_past_expires(self):
        """Available with past expiry → expired."""
        credit = _make_credit(
            status="available",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert credit.is_expired is True

    def test_available_past_expires_naive_datetime(self):
        """Edge case: naive datetime → treated as UTC."""
        credit = _make_credit(
            status="available",
            expires_at=datetime(2020, 1, 1),  # Naive, clearly in past
        )
        assert credit.is_expired is True

    def test_pending_not_expired(self):
        """Pending status with no expiry → not expired."""
        credit = _make_credit(status="pending", expires_at=None)
        assert credit.is_expired is False


# ──────────────────────────────────────────────────────────────
# is_available property
# ──────────────────────────────────────────────────────────────

class TestIsAvailable:
    def test_available_and_not_expired(self):
        credit = _make_credit(status="available", expires_at=None)
        assert credit.is_available is True

    def test_available_but_expired(self):
        credit = _make_credit(
            status="available",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert credit.is_available is False

    def test_not_available_status(self):
        credit = _make_credit(status="reserved")
        assert credit.is_available is False

    def test_forfeited_not_available(self):
        credit = _make_credit(status="forfeited")
        assert credit.is_available is False


# ──────────────────────────────────────────────────────────────
# __repr__
# ──────────────────────────────────────────────────────────────

class TestPlatformCreditRepr:
    def test_repr_includes_key_fields(self):
        credit = _make_credit(
            user_id="user_01ABC",
            amount_cents=5000,
            status="available",
        )
        result = repr(credit)
        assert "user_01ABC" in result
        assert "5000" in result
        assert "available" in result


# ──────────────────────────────────────────────────────────────
# Other model __repr__ methods
# ──────────────────────────────────────────────────────────────

class TestOtherPaymentModelsRepr:
    def test_stripe_customer_repr(self):
        from app.models.payment import StripeCustomer
        obj = StripeCustomer(
            user_id="user_01ABC",
            stripe_customer_id="cus_test",
        )
        result = repr(obj)
        assert "user_01ABC" in result

    def test_stripe_connected_account_repr(self):
        from app.models.payment import StripeConnectedAccount
        obj = StripeConnectedAccount(
            instructor_profile_id="prof_01ABC",
            stripe_account_id="acct_test",
            onboarding_completed=True,
        )
        result = repr(obj)
        assert "prof_01ABC" in result

    def test_payment_intent_repr(self):
        from app.models.payment import PaymentIntent
        obj = PaymentIntent(
            booking_id="bk_01ABC",
            stripe_payment_intent_id="pi_test",
            amount=5000,
            application_fee=500,
            status="succeeded",
        )
        result = repr(obj)
        assert "bk_01ABC" in result
        assert "5000" in result

    def test_payment_method_repr(self):
        from app.models.payment import PaymentMethod
        obj = PaymentMethod(
            user_id="user_01ABC",
            stripe_payment_method_id="pm_test",
            last4="4242",
            is_default=True,
        )
        result = repr(obj)
        assert "4242" in result

    def test_payment_event_repr(self):
        from app.models.payment import PaymentEvent
        obj = PaymentEvent(
            booking_id="bk_01ABC",
            event_type="captured",
        )
        result = repr(obj)
        assert "captured" in result

    def test_instructor_payout_event_repr(self):
        from app.models.payment import InstructorPayoutEvent
        obj = InstructorPayoutEvent(
            instructor_profile_id="prof_01ABC",
            stripe_account_id="acct_test",
            payout_id="po_test",
            amount_cents=10000,
        )
        result = repr(obj)
        assert "prof_01ABC" in result
