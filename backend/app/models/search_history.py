# backend/app/models/search_history.py
"""
Search History model for tracking user searches.

Tracks what users search for to enable features like:
- Recent searches display
- Search analytics
- Personalized recommendations
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class SearchHistory(Base):
    """
    Tracks user search queries for personalization.

    Stores search queries with their type and results count.
    Unique constraint on (user_id, search_query) prevents duplicates.
    """

    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Search details matching migration
    search_query = Column(Text, nullable=False)  # The exact search string
    search_type = Column(
        String(20), nullable=False, default="natural_language"
    )  # 'natural_language', 'category', or 'filter'
    results_count = Column(Integer, nullable=True)  # Number of results returned

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="search_history")
