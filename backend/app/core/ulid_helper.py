"""ULID generation helper utilities."""

from datetime import datetime
from typing import Optional

import ulid


def generate_ulid() -> str:
    """Generate a new ULID string."""
    return str(ulid.ULID())


def parse_ulid(ulid_str: str) -> Optional[ulid.ULID]:
    """Parse and validate a ULID string."""
    try:
        return ulid.from_str(ulid_str)
    except (ValueError, AttributeError):
        return None


def get_timestamp_from_ulid(ulid_str: str) -> Optional[datetime]:
    """Extract timestamp from ULID."""
    parsed = parse_ulid(ulid_str)
    if parsed:
        try:
            return parsed.timestamp().datetime
        except AttributeError:
            # Fallback for different ULID library versions
            return parsed.datetime
    return None


def is_valid_ulid(ulid_str: str) -> bool:
    """Check if a string is a valid ULID."""
    return parse_ulid(ulid_str) is not None
