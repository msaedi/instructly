# backend/app/schemas/search_context.py
"""
Search user context abstraction for unified search history handling.

This module provides a context object that abstracts the differences
between authenticated users and guests, allowing unified business logic.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, cast

from ..core.config import settings


@dataclass
class SearchUserContext:
    """
    Unified context for search operations that works for both authenticated users and guests.

    This abstraction allows us to write business logic once and have it work
    for both user types without duplication.
    """

    # One of these must be set
    user_id: Optional[int] = None
    guest_session_id: Optional[str] = None

    # Session tracking for analytics
    session_id: Optional[str] = None
    search_origin: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate that we have exactly one identifier."""
        if not (bool(self.user_id) ^ bool(self.guest_session_id)):
            raise ValueError("Must provide exactly one of user_id or guest_session_id")

    @classmethod
    def from_user(cls, user_id: int, session_id: Optional[str] = None) -> "SearchUserContext":
        """Create context for an authenticated user."""
        return cls(user_id=user_id, session_id=session_id)

    @classmethod
    def from_guest(
        cls, guest_session_id: str, session_id: Optional[str] = None
    ) -> "SearchUserContext":
        """Create context for a guest user."""
        return cls(guest_session_id=guest_session_id, session_id=session_id)

    @property
    def identifier(self) -> str:
        """Get the identifier as a string for logging."""
        if self.user_id:
            return f"user_{self.user_id}"
        return f"guest_{self.guest_session_id}"

    @property
    def is_authenticated(self) -> bool:
        """Check if this is an authenticated user."""
        return self.user_id is not None

    @property
    def search_limit(self) -> int:
        """Get the search history limit (same for both user types)."""
        return cast(int, settings.search_history_max_per_user)

    def to_repository_kwargs(self) -> Dict[str, Optional[Any]]:
        """
        Convert to kwargs for repository methods.

        This allows us to pass the context directly to repository methods
        that accept both user_id and guest_session_id parameters.
        """
        return {"user_id": self.user_id, "guest_session_id": self.guest_session_id}
