"""Tests for privacy-safe display helpers."""

from app.utils.privacy import format_private_display_name


def test_format_private_display_name_uses_default_user_fallback() -> None:
    """Missing names should fall back to a generic label."""
    assert format_private_display_name(None, None) == "User"
    assert format_private_display_name("", "   ") == "User"


def test_format_private_display_name_never_uses_email_as_fallback() -> None:
    """Email-like defaults should be sanitized to avoid privacy leaks."""
    assert (
        format_private_display_name(None, None, default="jane.doe@example.com")
        == "User"
    )


def test_format_private_display_name_keeps_contextual_non_email_defaults() -> None:
    """Context-specific labels should still be supported."""
    assert format_private_display_name(None, None, default="Student") == "Student"
