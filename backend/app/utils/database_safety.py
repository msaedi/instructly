"""Shared database safety helpers for destructive scripts."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from app.utils.env_logging import log_warn

HOSTED_DATABASE_HOST_PATTERNS = (
    "supabase.com",
    "supabase.co",
    "pooler.supabase.com",
)


def get_database_hostname(resolved_url: str) -> str:
    """Extract the hostname from a database URL."""
    try:
        return (urlparse(resolved_url).hostname or "").strip().lower()
    except Exception:
        return ""


def is_hosted_database_hostname(hostname: str) -> bool:
    normalized = (hostname or "").strip().lower()
    if not normalized:
        return False
    return any(
        normalized == pattern or normalized.endswith(f".{pattern}")
        for pattern in HOSTED_DATABASE_HOST_PATTERNS
    )


def check_hosted_database(env: str, resolved_url: str) -> None:
    """Apply destructive-script hostname safety rules."""
    hostname = get_database_hostname(resolved_url)
    if not is_hosted_database_hostname(hostname):
        return

    if env == "int":
        raise SystemExit(
            "Target is 'int' but resolved URL points to a hosted database. "
            "This is a misconfiguration. Aborting."
        )

    if env in {"preview", "stg"}:
        log_warn(env, f"Hosted database target detected: {hostname}")
        return

    if env != "prod":
        return

    if not sys.stdin.isatty():
        raise SystemExit(
            f"ERROR: Target is PRODUCTION database at {hostname}, but stdin is not a TTY. Aborting."
        )

    confirmation = input(
        f"⚠️  WARNING: Target is PRODUCTION database at {hostname}. "
        "Type the full hostname to proceed: "
    ).strip()
    if confirmation != hostname:
        raise SystemExit("ERROR: Hostname confirmation failed. Aborting.")
