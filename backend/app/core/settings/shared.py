from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Mapping, Set

from pydantic import SecretStr

logger = logging.getLogger(__name__)

NON_PROD_SITE_MODES: Set[str] = {
    "local",
    "dev",
    "development",
    "int",
    "stg",
    "stage",
    "staging",
    "preview",
}
PROD_SITE_MODES: Set[str] = {"prod", "production", "beta", "live"}

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SENDER_PROFILES_FILE = _BACKEND_ROOT / "config" / "email_senders.json"
DEFAULT_PRODUCTION_DATABASE_INDICATORS = [
    "supabase.com",
    "supabase.co",
    "amazonaws.com",
    "cloud.google.com",
    "database.azure.com",
    "elephantsql.com",
    "bit.io",
    "neon.tech",
    "railway.app",
    "render.com",
    "aiven.io",
]


def is_running_tests() -> bool:
    """Detect if code is running under pytest."""
    return os.getenv("PYTEST_CURRENT_TEST") is not None


def _classify_site_mode(raw_site_mode: str | None) -> tuple[str, bool, bool]:
    """Return normalized site mode with production/non-prod classification."""

    normalized = (raw_site_mode or "").strip().lower()
    is_prod = normalized in PROD_SITE_MODES
    is_non_prod = normalized in NON_PROD_SITE_MODES
    return normalized, is_prod, is_non_prod


def secret_or_plain(value: SecretStr | str | None, default: str = "") -> str:
    """Return the underlying string for SecretStr-like values."""

    if value is None:
        return default
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        try:
            return str(getter())
        except Exception as exc:
            raise ValueError(f"Failed to resolve secret: {type(value).__name__}") from exc
    return str(value)


def _default_secret_key() -> SecretStr:
    if os.getenv("CI"):
        return SecretStr("ci-test-secret-key-not-for-production")
    return SecretStr("")


def _default_int_database_url() -> SecretStr:
    if os.getenv("CI"):
        return SecretStr("postgresql://postgres:postgres@localhost:5432/instainstru_test")
    return SecretStr("")


def _default_session_cookie_name() -> str:
    """Return default session cookie name."""

    return "sid"


def _default_environment() -> str:
    return (
        "production" if _classify_site_mode(os.getenv("SITE_MODE", "local"))[1] else "development"
    )


def _default_production_database_indicators() -> list[str]:
    return list(DEFAULT_PRODUCTION_DATABASE_INDICATORS)


def resolve_referrals_step(
    *,
    raw_value: str | None = None,
    site_mode: str | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """
    Resolve REFERRALS_UNSAFE_STEP with safe defaults for non-production environments.

    When the env var is unset, return 4 for local/dev/stg-like modes so referral issuance
    remains enabled by default. Production defaults remain unchanged.
    """

    env_map = env or os.environ
    value = raw_value if raw_value is not None else env_map.get("REFERRALS_UNSAFE_STEP")
    cleaned = (value or "").strip()
    if cleaned:
        try:
            return max(0, int(cleaned))
        except ValueError:
            logger.warning("Invalid REFERRALS_UNSAFE_STEP=%s; defaulting to 0", cleaned)
            return 0

    normalized_mode, is_prod, is_non_prod = _classify_site_mode(
        site_mode or env_map.get("SITE_MODE")
    )
    if is_prod:
        return 0
    if is_non_prod or not normalized_mode:
        return 4
    return 4
