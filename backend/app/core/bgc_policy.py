"""Environment-aware helpers for background-check enforcement."""

from __future__ import annotations

from typing import Literal, Optional, cast

from .config import settings

BGCStatus = Literal["pending", "review", "passed", "failed"]


def must_be_verified_for_public() -> bool:
    """Return True when production should restrict listings/bookings to verified instructors."""

    # settings.site_mode uses the SITE_MODE env var under the hood; "prod" indicates production.
    site_mode = cast(str, settings.site_mode)
    return site_mode == "prod"


def is_verified(status: Optional[str]) -> bool:
    """Return True when the background-check status reflects a verified instructor."""

    return (status or "").strip().lower() == "passed"


__all__ = ["BGCStatus", "must_be_verified_for_public", "is_verified"]
