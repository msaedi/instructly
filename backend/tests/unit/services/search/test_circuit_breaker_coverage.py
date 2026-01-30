# backend/tests/unit/services/search/test_circuit_breaker_coverage.py
"""
Additional coverage tests for circuit breaker state machine.
Targets missed lines: 84-87, 94->exit, 100->exit, 111-114
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from app.services.search.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitBreakerStateTransitions:
    """Test state machine transitions that may not be covered."""

    def test_half_open_state_allows_attempt(self) -> None:
        """Lines 84-87: HALF_OPEN state should return True for _should_attempt()."""
        breaker = CircuitBreaker(
            name="test_half_open",
            config=CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=1,
                timeout_seconds=0.01,  # Very short timeout
            ),
        )

        # Trip the circuit to OPEN
        for _ in range(2):
            breaker._record_failure()

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout to allow HALF_OPEN
        time.sleep(0.02)

        # Now _should_attempt should transition to HALF_OPEN and return True
        result = breaker._should_attempt()
        assert result is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success_threshold(self) -> None:
        """Lines 94->exit: Successful calls in HALF_OPEN should close circuit."""
        breaker = CircuitBreaker(
            name="test_half_open_close",
            config=CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=2,  # Need 2 successes
                timeout_seconds=0.01,
            ),
        )

        # Manually set to HALF_OPEN
        breaker._state = CircuitState.HALF_OPEN
        breaker._success_count = 0

        # First success - not enough yet
        breaker._record_success()
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker._success_count == 1

        # Second success - should close
        breaker._record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0
        assert breaker._success_count == 0

    def test_closed_state_resets_failure_count_on_success(self) -> None:
        """Lines 100->exit: Success in CLOSED state resets failure count."""
        breaker = CircuitBreaker(
            name="test_closed_reset",
            config=CircuitBreakerConfig(failure_threshold=5),
        )

        # Accumulate some failures (but not enough to open)
        for _ in range(3):
            breaker._record_failure()

        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 3

        # A success should reset the failure count
        breaker._record_success()
        assert breaker._failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self) -> None:
        """Lines 111-114: Any failure in HALF_OPEN goes back to OPEN."""
        breaker = CircuitBreaker(
            name="test_half_open_fail",
            config=CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=2,
                timeout_seconds=60.0,
            ),
        )

        # Manually set to HALF_OPEN with some success progress
        breaker._state = CircuitState.HALF_OPEN
        breaker._success_count = 1

        # A failure should immediately go back to OPEN
        breaker._record_failure()

        assert breaker.state == CircuitState.OPEN
        assert breaker._success_count == 0

    def test_open_state_blocks_attempts(self) -> None:
        """OPEN state should block attempts until timeout."""
        breaker = CircuitBreaker(
            name="test_open_block",
            config=CircuitBreakerConfig(
                failure_threshold=2,
                timeout_seconds=60.0,  # Long timeout
            ),
        )

        # Trip the circuit
        for _ in range(2):
            breaker._record_failure()

        assert breaker.state == CircuitState.OPEN

        # Should not allow attempt (no timeout elapsed)
        result = breaker._should_attempt()
        assert result is False
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_call_raises_when_open(self) -> None:
        """call() should raise CircuitOpenError when circuit is OPEN."""
        breaker = CircuitBreaker(
            name="test_call_open",
            config=CircuitBreakerConfig(
                failure_threshold=1,
                timeout_seconds=60.0,
            ),
        )

        # Trip the circuit
        breaker._record_failure()
        assert breaker.state == CircuitState.OPEN

        # call() should raise
        with pytest.raises(CircuitOpenError) as exc_info:
            await breaker.call(AsyncMock())

        assert "test_call_open" in str(exc_info.value)
        assert "OPEN" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_circuit_call_records_success(self) -> None:
        """Successful call should record success."""
        breaker = CircuitBreaker(
            name="test_call_success",
            config=CircuitBreakerConfig(failure_threshold=5),
        )

        # Add some failures first
        breaker._record_failure()
        breaker._record_failure()
        assert breaker._failure_count == 2

        # Successful call
        mock_func = AsyncMock(return_value="result")
        result = await breaker.call(mock_func)

        assert result == "result"
        assert breaker._failure_count == 0  # Reset on success

    @pytest.mark.asyncio
    async def test_circuit_call_records_failure_and_reraises(self) -> None:
        """Failed call should record failure and re-raise exception."""
        breaker = CircuitBreaker(
            name="test_call_failure",
            config=CircuitBreakerConfig(failure_threshold=5),
        )

        # Create a function that raises
        mock_func = AsyncMock(side_effect=ValueError("test error"))

        with pytest.raises(ValueError, match="test error"):
            await breaker.call(mock_func)

        assert breaker._failure_count == 1

    def test_is_open_property(self) -> None:
        """is_open property should reflect OPEN state."""
        breaker = CircuitBreaker(
            name="test_is_open",
            config=CircuitBreakerConfig(failure_threshold=2),
        )

        assert breaker.is_open is False

        # Trip it
        breaker._record_failure()
        breaker._record_failure()

        assert breaker.is_open is True

    def test_reset_from_half_open(self) -> None:
        """Manual reset from HALF_OPEN state should work."""
        breaker = CircuitBreaker(
            name="test_reset_half_open",
            config=CircuitBreakerConfig(failure_threshold=2, success_threshold=3),
        )

        # Set to HALF_OPEN with some progress
        breaker._state = CircuitState.HALF_OPEN
        breaker._success_count = 2
        breaker._failure_count = 1

        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker._success_count == 0
        assert breaker._failure_count == 0


class TestCircuitBreakerEdgeCases:
    """Edge cases and boundary conditions."""

    def test_exact_failure_threshold_trips_circuit(self) -> None:
        """Circuit should trip exactly at failure threshold."""
        breaker = CircuitBreaker(
            name="test_exact_threshold",
            config=CircuitBreakerConfig(failure_threshold=3),
        )

        breaker._record_failure()
        assert breaker.state == CircuitState.CLOSED
        breaker._record_failure()
        assert breaker.state == CircuitState.CLOSED
        breaker._record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_success_threshold_one_immediate_recovery(self) -> None:
        """With success_threshold=1, single success should close circuit."""
        breaker = CircuitBreaker(
            name="test_single_success",
            config=CircuitBreakerConfig(
                failure_threshold=1,
                success_threshold=1,
            ),
        )

        # Set to HALF_OPEN
        breaker._state = CircuitState.HALF_OPEN

        # Single success should close
        breaker._record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_timeout_boundary_exact(self) -> None:
        """Test timeout at exact boundary."""
        breaker = CircuitBreaker(
            name="test_timeout_boundary",
            config=CircuitBreakerConfig(
                failure_threshold=1,
                timeout_seconds=0.05,
            ),
        )

        # Trip circuit
        breaker._record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait just under timeout
        time.sleep(0.03)
        result = breaker._should_attempt()
        assert result is False
        assert breaker.state == CircuitState.OPEN

        # Wait past timeout
        time.sleep(0.03)
        result = breaker._should_attempt()
        assert result is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_state_property_thread_safe(self) -> None:
        """State property should be thread-safe (uses lock)."""
        breaker = CircuitBreaker(
            name="test_thread_safe",
            config=CircuitBreakerConfig(failure_threshold=2),
        )

        # Access state multiple times should work
        for _ in range(10):
            _ = breaker.state

        assert breaker.state == CircuitState.CLOSED

    def test_failure_during_closed_not_enough_to_trip(self) -> None:
        """Failures below threshold should keep circuit closed."""
        breaker = CircuitBreaker(
            name="test_under_threshold",
            config=CircuitBreakerConfig(failure_threshold=10),
        )

        for _ in range(9):
            breaker._record_failure()

        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 9

    @pytest.mark.asyncio
    async def test_circuit_call_in_half_open_success(self) -> None:
        """Successful call in HALF_OPEN should contribute to closing."""
        breaker = CircuitBreaker(
            name="test_half_open_call",
            config=CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=1,
                timeout_seconds=0.01,
            ),
        )

        # Trip and wait for half-open
        for _ in range(2):
            breaker._record_failure()
        time.sleep(0.02)

        # Successful call should close circuit
        mock_func = AsyncMock(return_value="ok")
        result = await breaker.call(mock_func)

        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_call_in_half_open_failure(self) -> None:
        """Failed call in HALF_OPEN should re-open circuit."""
        breaker = CircuitBreaker(
            name="test_half_open_fail_call",
            config=CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=2,
                timeout_seconds=0.01,
            ),
        )

        # Trip and wait for half-open
        for _ in range(2):
            breaker._record_failure()
        time.sleep(0.02)

        # First call should put us in HALF_OPEN
        assert breaker._should_attempt() is True
        assert breaker.state == CircuitState.HALF_OPEN

        # Failed call should re-open circuit
        mock_func = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            await breaker.call(mock_func)

        assert breaker.state == CircuitState.OPEN
