"""
Timezone utilities for InstaInstru platform.

Provides user-based timezone support while maintaining NYC as default.
This allows the platform to scale beyond NYC in the future.
"""

from datetime import date, datetime
from typing import Optional

import pytz
from sqlalchemy.orm import Session

# Default timezone for the platform (NYC for now)
DEFAULT_TIMEZONE = pytz.timezone("America/New_York")


def get_user_timezone(user_id: Optional[int] = None, db: Optional[Session] = None) -> pytz.timezone:
    """
    Get user's timezone preference.

    Args:
        user_id: User ID to look up timezone for
        db: Database session (for future user timezone lookup)

    Returns:
        User's timezone or default NYC timezone
    """
    # For now, always return NYC timezone
    # TODO: When user timezone preferences are added, query from database
    # if user_id and db:
    #     user = db.query(User).filter(User.id == user_id).first()
    #     if user and user.timezone:
    #         return pytz.timezone(user.timezone)

    return DEFAULT_TIMEZONE


def get_user_today(user_id: Optional[int] = None, db: Optional[Session] = None) -> date:
    """
    Get 'today' in the user's timezone.

    Args:
        user_id: User ID to get timezone for
        db: Database session

    Returns:
        Today's date in user's timezone
    """
    user_tz = get_user_timezone(user_id, db)
    return datetime.now(user_tz).date()


def get_user_now(user_id: Optional[int] = None, db: Optional[Session] = None) -> datetime:
    """
    Get current datetime in user's timezone.

    Args:
        user_id: User ID to get timezone for
        db: Database session

    Returns:
        Current datetime in user's timezone
    """
    user_tz = get_user_timezone(user_id, db)
    return datetime.now(user_tz)


def convert_to_user_timezone(dt: datetime, user_id: Optional[int] = None, db: Optional[Session] = None) -> datetime:
    """
    Convert UTC datetime to user's timezone.

    Args:
        dt: Datetime to convert
        user_id: User ID to get timezone for
        db: Database session

    Returns:
        Datetime in user's timezone
    """
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = pytz.UTC.localize(dt)

    user_tz = get_user_timezone(user_id, db)
    return dt.astimezone(user_tz)


def format_datetime_for_user(dt: datetime, user_id: Optional[int] = None, db: Optional[Session] = None) -> dict:
    """
    Format datetime with timezone info for frontend.

    Args:
        dt: Datetime to format
        user_id: User ID to get timezone for
        db: Database session

    Returns:
        Dictionary with various datetime formats
    """
    user_dt = convert_to_user_timezone(dt, user_id, db)

    return {
        "iso": dt.isoformat(),  # UTC ISO format
        "local": user_dt.isoformat(),  # User's timezone
        "timezone": str(get_user_timezone(user_id, db)),
        "date": user_dt.date().isoformat(),
        "time": user_dt.time().isoformat(),
    }
