"""
Timezone utilities for InstaInstru platform.

Provides user-based timezone support.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

import pytz
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.user import User


def get_user_timezone(user: "User") -> pytz.timezone:
    """
    Get user's timezone preference.

    Args:
        user: User object (always has timezone field)

    Returns:
        User's timezone as pytz timezone object
    """
    return pytz.timezone(user.timezone)


def get_user_today(user: "User") -> date:
    """
    Get 'today' in the user's timezone.

    Args:
        user: User object

    Returns:
        Today's date in user's timezone
    """
    user_tz = get_user_timezone(user)
    return datetime.now(user_tz).date()


def get_user_now(user: "User") -> datetime:
    """
    Get current datetime in user's timezone.

    Args:
        user: User object

    Returns:
        Current datetime in user's timezone
    """
    user_tz = get_user_timezone(user)
    return datetime.now(user_tz)


def convert_to_user_timezone(dt: datetime, user: "User") -> datetime:
    """
    Convert UTC datetime to user's timezone.

    Args:
        dt: Datetime to convert
        user: User object

    Returns:
        Datetime in user's timezone
    """
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = pytz.UTC.localize(dt)

    user_tz = get_user_timezone(user)
    return dt.astimezone(user_tz)


def format_datetime_for_user(dt: datetime, user: "User") -> dict:
    """
    Format datetime with timezone info for frontend.

    Args:
        dt: Datetime to format
        user: User object

    Returns:
        Dictionary with various datetime formats
    """
    user_dt = convert_to_user_timezone(dt, user)

    return {
        "iso": dt.isoformat(),  # UTC ISO format
        "local": user_dt.isoformat(),  # User's timezone
        "timezone": str(get_user_timezone(user)),
        "date": user_dt.date().isoformat(),
        "time": user_dt.time().isoformat(),
    }


def get_user_today_by_id(user_id: int, db: Session) -> date:
    """
    Get today's date for a user by ID.

    This helper is used by cached repository methods that work with user IDs
    rather than User objects to maintain efficient cache keys.

    Args:
        user_id: The ID of the user
        db: Database session to fetch user

    Returns:
        Today's date in user's timezone

    Raises:
        ValueError: If user not found
    """
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User with id {user_id} not found")
    return get_user_today(user)
