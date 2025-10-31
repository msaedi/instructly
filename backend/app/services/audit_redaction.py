# backend/app/services/audit_redaction.py
"""
Helpers for audit payload redaction.

Performs a shallow sanitization step to strip obvious PII/secret fields before
persisting audit snapshots.
"""

from __future__ import annotations

from typing import Any

REDACTED_VALUE = "[REDACTED]"

_EXACT_KEYS = {
    "email",
    "phone",
    "phone_number",
    "client_secret",
    "access_token",
    "refresh_token",
    "ssn",
    "social_security_number",
    "student_note",
    "instructor_note",
    "meeting_location",
}

_PREFIX_KEYS = (
    "payment_",
    "card_",
    "bank_account",
    "stripe_",
)

_SUFFIX_KEYS = (
    "_token",
    "_secret",
    "_client_secret",
    "_api_key",
)


def redact(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a shallow redacted copy of the payload."""
    if obj is None:
        return None

    sanitized: dict[str, Any] = {}

    for key, value in obj.items():
        lowered = key.lower()
        if (
            lowered in _EXACT_KEYS
            or any(lowered.startswith(prefix) for prefix in _PREFIX_KEYS)
            or any(lowered.endswith(suffix) for suffix in _SUFFIX_KEYS)
        ):
            sanitized[key] = REDACTED_VALUE
            continue
        sanitized[key] = value

    return sanitized
