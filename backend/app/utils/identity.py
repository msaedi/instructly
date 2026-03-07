"""Helpers for identity cross-checking and safe logging."""

from typing import Any


def clean_identity_value(value: Any) -> str | None:
    """Return a trimmed string value or ``None`` when empty."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


# Design decision: only last names are compared for identity mismatch.
# First names legitimately differ (Mike vs Michael, Bob vs Robert, nicknames).
# Last names are the reliable anchor for identity cross-checking.
def normalize_name(value: Any) -> str | None:
    """Strip and lowercase a name value for comparison."""
    cleaned = clean_identity_value(value)
    return cleaned.lower() if cleaned else None


def redact_name(value: Any) -> str:
    """Redact name values in logs: ``Johnson`` becomes ``J****(7)``."""
    cleaned = clean_identity_value(value)
    if not cleaned:
        return "<empty>"
    return f"{cleaned[0]}****({len(cleaned)})"
