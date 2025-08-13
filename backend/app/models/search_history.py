# backend/app/models/search_history.py
"""
Search History model for tracking deduplicated user searches.

This is the user-facing table that provides a clean UX by deduplicating
searches. When a user searches for the same term multiple times, we
increment the count rather than creating duplicate entries.

Features:
- Deduplicated recent searches display
- Search frequency tracking
- Guest session tracking
- Soft deletes for data retention
- Conversion tracking when guests become users
"""

import ulid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class SearchHistory(Base):
    """
    Tracks user and guest search queries for personalization and analytics.

    Supports:
    - User and guest searches (user_id OR guest_session_id)
    - Soft deletes for analytics retention
    - Conversion tracking when guests become users
    """

    __tablename__ = "search_history"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)  # Nullable for guests

    # Search details matching migration
    search_query = Column(Text, nullable=False)  # The exact search string
    normalized_query = Column(String, nullable=False)  # Lowercase, trimmed for deduplication
    search_type = Column(
        String(20), nullable=False, default="natural_language"
    )  # 'natural_language', 'category', 'service_pill', 'filter', or 'search_history'
    results_count = Column(Integer, nullable=True)  # Number of results returned

    # Hybrid model columns for deduplication
    search_count = Column(Integer, nullable=False, default=1)  # How many times searched
    first_searched_at = Column(DateTime(timezone=True), server_default=func.timezone("UTC", func.now()), nullable=False)
    last_searched_at = Column(DateTime(timezone=True), server_default=func.timezone("UTC", func.now()), nullable=False)

    # Soft delete support
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Guest session tracking
    guest_session_id = Column(String(36), nullable=True, index=True)  # UUID for guest sessions
    converted_to_user_id = Column(String(26), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # Primary user relationship (for users who performed the search)
    user = relationship("User", foreign_keys=[user_id], back_populates="search_history")
    # Converted user relationship (for tracking guest-to-user conversions)
    # No back_populates since User model doesn't have a converted_searches relationship
    converted_user = relationship("User", foreign_keys=[converted_to_user_id])
