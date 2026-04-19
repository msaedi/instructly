"""Typed exceptions for Stripe webhook processing.

Separating retryable from permanent failures lets the webhook endpoint map them
to the correct HTTP response: 503 for transient errors (so Stripe retries) vs.
200 for permanent errors (so Stripe does not).
"""

from __future__ import annotations


class WebhookRetryableError(Exception):
    """Raised when a webhook fails due to a transient condition and should be
    retried by Stripe. The endpoint converts this to HTTP 503."""


class WebhookPermanentError(Exception):
    """Raised when a webhook fails due to a non-retryable condition (malformed
    input, bad state, programming error). The endpoint converts this to HTTP 200
    so Stripe stops retrying, and the event is marked failed in the ledger."""
