# backend/app/models/search_history.py
"""
Search History model for tracking user searches.

Tracks what users search for to enable features like:
- Recent searches display
- Search analytics
- Personalized recommendations
- Guest session tracking
- Soft deletes for data retention
"""

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

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)  # Nullable for guests

    # Search details matching migration
    search_query = Column(Text, nullable=False)  # The exact search string
    search_type = Column(
        String(20), nullable=False, default="natural_language"
    )  # 'natural_language', 'category', 'service_pill', or 'filter'
    results_count = Column(Integer, nullable=True)  # Number of results returned

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.timezone("UTC", func.now()), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Soft delete support

    # Guest session tracking
    guest_session_id = Column(String(36), nullable=True, index=True)  # UUID for guest sessions
    converted_to_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # Primary user relationship (for users who performed the search)
    user = relationship("User", foreign_keys=[user_id], back_populates="search_history")
    # Converted user relationship (for tracking guest-to-user conversions)
    # No back_populates since User model doesn't have a converted_searches relationship
    converted_user = relationship("User", foreign_keys=[converted_to_user_id])
