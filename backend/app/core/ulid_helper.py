"""ULID generation helper utilities."""

from datetime import datetime
from typing import Optional, cast

import ulid


def generate_ulid() -> str:
    """Generate a new ULID string."""
    return str(ulid.ULID())


def parse_ulid(ulid_str: str) -> Optional[ulid.ULID]:
    """Parse and validate a ULID string."""
    try:
        return ulid.ULID.from_str(str(ulid_str).upper())
    except (ValueError, AttributeError):
        return None


def get_timestamp_from_ulid(ulid_str: str) -> Optional[datetime]:
    """Extract timestamp from ULID."""
    parsed = parse_ulid(ulid_str)
    if parsed:
        try:
            timestamp_attr = getattr(parsed, "timestamp", None)
            if callable(timestamp_attr):
                timestamp_obj = timestamp_attr()
            else:
                timestamp_obj = timestamp_attr
            if hasattr(timestamp_obj, "datetime"):
                return cast(datetime, timestamp_obj.datetime)
        except (AttributeError, TypeError):
            pass
        if hasattr(parsed, "datetime"):
            return cast(datetime, parsed.datetime)
    return None


def is_valid_ulid(ulid_str: str) -> bool:
    """Check if a string is a valid ULID."""
    return parse_ulid(ulid_str) is not None
