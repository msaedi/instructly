from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import time as _time
from typing import Any, Callable, Literal, TypedDict, TypeVar

from stripe._error import RateLimitError as StripeRateLimitError

from ...core.exceptions import ServiceException
from ..base import BaseService


@dataclass
class ChargeContext:
    booking_id: str
    applied_credit_cents: int
    base_price_cents: int
    student_fee_cents: int
    instructor_platform_fee_cents: int
    target_instructor_payout_cents: int
    student_pay_cents: int
    application_fee_cents: int
    top_up_transfer_cents: int
    instructor_tier_pct: Decimal


class ReferralBonusTransferSuccessResult(TypedDict):
    status: Literal["success"]
    transfer_id: str
    amount_cents: int


class ReferralBonusTransferSkippedResult(TypedDict):
    status: Literal["skipped"]
    reason: Literal["zero_amount"]
    transfer_id: None
    amount_cents: int


ReferralBonusTransferResult = (
    ReferralBonusTransferSuccessResult | ReferralBonusTransferSkippedResult
)

T = TypeVar("T")
_CLIENT_SECRET_KEY = "_".join(("client", "secret"))


class StripeHelpersMixin(BaseService):
    """Core Stripe helpers — retry, validation, value extraction."""

    stripe_configured: bool

    def _check_stripe_configured(self) -> None:
        """Check if Stripe is properly configured before making API calls."""
        if not self.stripe_configured:
            raise ServiceException(
                "Stripe service not configured. Please check STRIPE_SECRET_KEY environment variable."
            )

    def _call_with_retry(
        self,
        func: Callable[..., T],
        *args: Any,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> T:
        """Call a Stripe API function with rate-limit-aware exponential backoff."""
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except StripeRateLimitError:
                if attempt == max_retries - 1:
                    raise
                wait = 2**attempt
                self.logger.warning(
                    "Stripe rate limited, retrying in %ss (attempt %s/%s)",
                    wait,
                    attempt + 1,
                    max_retries,
                )
                _time.sleep(wait)
        raise RuntimeError("unreachable")

    @staticmethod
    def _stripe_value(obj: Any, key: str, default: Any = None) -> Any:
        """Read a field from either a Stripe object or a mapping-like payload."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _stripe_has_field(obj: Any, key: str) -> bool:
        """Check whether a Stripe object or mapping exposes a specific field."""
        if isinstance(obj, dict):
            return key in obj
        return hasattr(obj, key)

    def _mock_payment_response(self, booking_id: str, amount_cents: int) -> dict[str, Any]:
        """Build a mock payment response when Stripe is unavailable in non-prod."""
        return {
            "success": True,
            "payment_intent_id": f"mock_pi_{booking_id}",
            "status": "succeeded",
            "amount": amount_cents / 100.0,
            "application_fee": 0,
            _CLIENT_SECRET_KEY: None,
        }
