# backend/app/models/search_event.py
"""
Search Event Model for analytics tracking.

This model stores every search event for analytics purposes,
maintaining a complete history of all searches without deduplication.
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class SearchEvent(Base):
    """
    Append-only event log for search analytics.

    Unlike SearchHistory which deduplicates for UX, this table
    records every single search event for analytics and tracking.
    """

    __tablename__ = "search_events"

    id = Column(Integer, primary_key=True, index=True)

    # User identification (one or the other)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    guest_session_id = Column(String(36), nullable=True, index=True)

    # Search details
    search_query = Column(Text, nullable=False, index=True)
    search_type = Column(
        String(20),
        nullable=False,
        default="natural_language",
        comment="Type of search: natural_language, category, service_pill, filter, search_history",
    )
    results_count = Column(Integer, default=0, nullable=True)

    # Event tracking
    searched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    session_id = Column(String(36), nullable=True, index=True, comment="Browser session for journey tracking")
    referrer = Column(String(255), nullable=True, comment="Page where search originated")

    # Additional context as JSON
    search_context = Column(JSON, nullable=True, comment="Additional context: filters, location, device info, etc.")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<SearchEvent(id={self.id}, query='{self.search_query[:30]}...', user_id={self.user_id})>"
