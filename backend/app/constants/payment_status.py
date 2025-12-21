"""Shared payment status mapping helpers."""

from __future__ import annotations

from enum import Enum
from typing import Optional


class PaymentDisplayStatus(str, Enum):
    AUTHORIZED = "authorized"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
    PENDING = "pending"


STRIPE_TO_DISPLAY_STATUS = {
    "requires_capture": PaymentDisplayStatus.AUTHORIZED,
    "succeeded": PaymentDisplayStatus.PAID,
    "failed": PaymentDisplayStatus.FAILED,
    "refunded": PaymentDisplayStatus.REFUNDED,
    "canceled": PaymentDisplayStatus.CANCELLED,
    "cancelled": PaymentDisplayStatus.CANCELLED,
    "requires_payment_method": PaymentDisplayStatus.PENDING,
    "requires_confirmation": PaymentDisplayStatus.PENDING,
    "processing": PaymentDisplayStatus.PENDING,
}


def map_payment_status(stripe_status: Optional[str]) -> str:
    """Map Stripe payment status to display status for UI."""
    if not stripe_status:
        return PaymentDisplayStatus.PENDING.value
    mapped = STRIPE_TO_DISPLAY_STATUS.get(stripe_status)
    if mapped is None:
        return stripe_status
    return mapped.value
