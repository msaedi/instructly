"""Privacy-safe display helpers for participant identity."""

from __future__ import annotations

from .identity import clean_identity_value


def format_last_initial(last_name: str | None, *, with_period: bool = False) -> str:
    """Return the last-name initial or an empty string when unavailable."""
    cleaned = clean_identity_value(last_name)
    if not cleaned:
        return ""
    initial = cleaned[0].upper()
    return f"{initial}." if with_period else initial


def format_private_display_name(
    first_name: str | None,
    last_name: str | None,
    *,
    default: str = "User",
) -> str:
    """Return ``First L.`` for counterparties without leaking email-like fallbacks."""
    cleaned_first = clean_identity_value(first_name)
    last_initial = format_last_initial(last_name, with_period=True)
    fallback = clean_identity_value(default) or "User"
    if "@" in fallback:
        fallback = "User"
    if cleaned_first and last_initial:
        return f"{cleaned_first} {last_initial}"
    if cleaned_first:
        return cleaned_first
    return fallback
