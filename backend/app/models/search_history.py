# backend/app/models/search_history.py
"""
Search History model for tracking user searches.

Tracks what users search for to enable features like:
- Recent searches display
- Search analytics
- Personalized recommendations
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database import Base


class SearchHistory(Base):
    """
    Tracks user search queries for personalization.

    Stores the full search context including query, filters,
    and results count for analytics.
    """

    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Search details
    query = Column(String, nullable=False)  # The search text
    filters = Column(JSON, default={})  # Any filters applied
    results_count = Column(Integer, default=0)  # Number of results returned

    # Optional context
    service_category = Column(String, nullable=True)  # If searching within a category
    location = Column(String, nullable=True)  # If location-specific search

    # Timestamps
    searched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="search_history")
