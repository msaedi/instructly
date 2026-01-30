# backend/tests/ratelimit/test_gcra_coverage_r5.py
"""
Round 5 Coverage Tests for GCRA (Generic Cell Rate Algorithm).

Target: Raise coverage from 85.00% to 92%+
Missed lines: 16, 43-47 (zero rate handling)
"""

import time

from app.ratelimit.gcra import Decision, _to_interval_s, gcra_decide


class TestToIntervalFunction:
    """Tests for _to_interval_s helper function."""

    def test_zero_rate_returns_infinity(self):
        """Line 16: rate_per_min <= 0 returns infinity."""
        result = _to_interval_s(0)
        assert result == float("inf")

    def test_negative_rate_returns_infinity(self):
        """Line 16: Negative rate returns infinity."""
        result = _to_interval_s(-5)
        assert result == float("inf")

    def test_positive_rate_returns_interval(self):
        """Normal positive rate returns calculated interval."""
        # 60 requests per minute = 1 second interval
        result = _to_interval_s(60)
        assert result == 1.0

        # 6 requests per minute = 10 seconds interval
        result = _to_interval_s(6)
        assert result == 10.0


class TestGCRAZeroRateHandling:
    """Tests for GCRA with zero rate (Lines 43-47)."""

    def test_zero_rate_always_blocked(self):
        """Lines 42-47: Zero rate means always blocked."""
        now = time.time()
        tat = None
        rate = 0  # Zero rate - should block everything
        burst = 5

        new_tat, decision = gcra_decide(now, tat, rate, burst)

        # Should be blocked
        assert decision.allowed is False
        assert decision.retry_after_s == float("inf")
        assert decision.remaining == 0
        assert decision.limit == 0
        assert decision.reset_epoch_s == float("inf")

    def test_zero_rate_with_existing_tat(self):
        """Lines 43-47: Zero rate with existing TAT still blocked."""
        now = time.time()
        existing_tat = now - 100  # TAT from 100 seconds ago
        rate = 0
        burst = 3

        new_tat, decision = gcra_decide(now, existing_tat, rate, burst)

        assert decision.allowed is False
        assert decision.retry_after_s == float("inf")
        # Should preserve existing TAT
        assert new_tat == existing_tat

    def test_zero_rate_returns_original_tat_or_now(self):
        """Line 47: Returns last_tat_s or now_s for zero rate."""
        now = time.time()

        # With no TAT - should return now
        new_tat, _ = gcra_decide(now, None, 0, 5)
        assert new_tat == now

        # With existing TAT - should return existing TAT
        existing_tat = now - 50
        new_tat, _ = gcra_decide(now, existing_tat, 0, 5)
        assert new_tat == existing_tat


class TestGCRAEdgeCases:
    """Additional edge case tests for full coverage."""

    def test_negative_rate_treated_as_zero(self):
        """Negative rate should behave like zero rate."""
        now = time.time()

        new_tat, decision = gcra_decide(now, None, -10, 5)

        assert decision.allowed is False
        assert decision.retry_after_s == float("inf")

    def test_decision_dataclass_fields(self):
        """Verify Decision dataclass has all expected fields."""
        decision = Decision(
            allowed=True,
            retry_after_s=0.0,
            remaining=5,
            limit=10,
            reset_epoch_s=1234567890.0
        )

        assert decision.allowed is True
        assert decision.retry_after_s == 0.0
        assert decision.remaining == 5
        assert decision.limit == 10
        assert decision.reset_epoch_s == 1234567890.0

    def test_zero_burst_with_zero_rate(self):
        """Zero rate with zero burst should still be blocked."""
        now = time.time()

        new_tat, decision = gcra_decide(now, None, 0, 0)

        assert decision.allowed is False

    def test_blocked_decision_retry_after_calculation(self):
        """Test that blocked requests get proper retry_after."""
        now = time.time()
        rate = 60  # 1 per second
        burst = 0

        # First request allowed
        tat, decision1 = gcra_decide(now, None, rate, burst)
        assert decision1.allowed is True

        # Immediate second request blocked
        tat, decision2 = gcra_decide(now, tat, rate, burst)
        assert decision2.allowed is False
        assert decision2.retry_after_s > 0
        assert decision2.retry_after_s <= 1.0  # Should be about 1 second

    def test_allowed_after_waiting(self):
        """Request should be allowed after waiting retry_after time."""
        now = time.time()
        rate = 60  # 1 per second
        burst = 0

        # First request
        tat, _ = gcra_decide(now, None, rate, burst)

        # Second request immediately - blocked
        tat, decision = gcra_decide(now, tat, rate, burst)
        assert decision.allowed is False

        # Third request after waiting
        later = now + decision.retry_after_s + 0.1
        tat, decision = gcra_decide(later, tat, rate, burst)
        assert decision.allowed is True
