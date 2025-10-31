from copy import deepcopy

from app.services.audit_redaction import REDACTED_VALUE, redact


def test_redact_masks_sensitive_fields() -> None:
    payload = {
        "email": "user@example.com",
        "student_note": "Call me at 555-0000",
        "meeting_location": "123 Secret St",
        "payment_token": "tok_abc123",
        "card_number": "4242424242424242",
        "display_name": "Friendly Name",
    }

    original = deepcopy(payload)

    sanitized = redact(payload)

    assert sanitized is not None
    assert sanitized["email"] == REDACTED_VALUE
    assert sanitized["student_note"] == REDACTED_VALUE
    assert sanitized["meeting_location"] == REDACTED_VALUE
    assert sanitized["payment_token"] == REDACTED_VALUE
    assert sanitized["card_number"] == REDACTED_VALUE
    assert sanitized["display_name"] == "Friendly Name"

    # Ensure original dict not mutated
    assert payload == original


def test_redact_handles_none() -> None:
    assert redact(None) is None
