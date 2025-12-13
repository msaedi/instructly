# backend/app/services/search/circuit_breaker.py
"""
Circuit breaker pattern for external service protection.
Prevents cascade failures when OpenAI API is degraded.
"""
from dataclasses import dataclass, field
from enum import Enum
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 1  # Successes to close from half-open
    timeout_seconds: float = 60.0  # Time before trying half-open
    window_seconds: float = 30.0  # Window for counting failures


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for protecting external service calls.

    Usage:
        breaker = CircuitBreaker(name="openai_parsing")

        try:
            result = await breaker.call(async_function, *args)
        except CircuitOpenError:
            # Use fallback
    """

    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    # State
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: Optional[float] = field(default=None, init=False)
    _last_state_change: float = field(default_factory=time.time, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def _should_attempt(self) -> bool:
        """Check if we should attempt the call."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if timeout has passed
                elapsed = time.time() - self._last_state_change
                if elapsed >= self.config.timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._last_state_change = time.time()
                    logger.info(f"Circuit {self.name}: OPEN -> HALF_OPEN")
                    return True
                return False

            if self._state == CircuitState.HALF_OPEN:
                return True

            return False

    def _record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._last_state_change = time.time()
                    logger.info(f"Circuit {self.name}: HALF_OPEN -> CLOSED")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def _record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._state = CircuitState.OPEN
                self._last_state_change = time.time()
                self._success_count = 0
                logger.warning(f"Circuit {self.name}: HALF_OPEN -> OPEN (test failed)")

            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._last_state_change = time.time()
                    logger.warning(
                        f"Circuit {self.name}: CLOSED -> OPEN " f"({self._failure_count} failures)"
                    )

    async def call(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through the circuit breaker.

        Raises:
            CircuitOpenError: If circuit is open and not ready to test
        """
        if not self._should_attempt():
            raise CircuitOpenError(f"Circuit {self.name} is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_state_change = time.time()
            logger.info(f"Circuit {self.name}: Manually reset to CLOSED")


class CircuitOpenError(Exception):
    """Raised when attempting to call through an open circuit."""

    pass


# Pre-configured circuit breakers for NL Search
PARSING_CIRCUIT = CircuitBreaker(
    name="openai_parsing",
    config=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60.0,
        window_seconds=30.0,
    ),
)

EMBEDDING_CIRCUIT = CircuitBreaker(
    name="openai_embedding",
    config=CircuitBreakerConfig(
        failure_threshold=3,
        timeout_seconds=60.0,
        window_seconds=30.0,
    ),
)
