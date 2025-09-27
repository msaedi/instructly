# backend/app/models/search_interaction.py
"""
Search Interaction Model for tracking user engagement with search results.

This model tracks how users interact with search results, including clicks,
hovers, bookmarks, and other engagement metrics.
"""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base


class SearchInteraction(Base):
    """
    Tracks user interactions with search results.

    This model records detailed interaction data to help understand:
    - Which search results users click on
    - How long it takes users to find what they're looking for
    - Which instructors get the most engagement from searches
    - Search result quality and relevance
    """

    __tablename__ = "search_interactions"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Link to the search event
    search_event_id = Column(
        String(26), ForeignKey("search_events.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Session tracking
    session_id = Column(String(36), nullable=True, comment="Browser session ID")

    # Interaction details
    interaction_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of interaction: click, hover, bookmark, view_profile, contact, book",
    )

    # Result details
    instructor_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ID of the instructor whose result was interacted with",
    )
    result_position = Column(
        Integer, nullable=True, comment="Position of the result in search results (1-based)"
    )

    # Timing metrics
    time_to_interaction = Column(Float, nullable=True, comment="Seconds from search to interaction")
    interaction_duration = Column(
        Float, nullable=True, comment="Duration of interaction in seconds (e.g., hover time)"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    search_event = relationship("SearchEvent", backref="interactions")
    instructor = relationship("User", foreign_keys=[instructor_id])

    def __repr__(self) -> str:
        return f"<SearchInteraction(id={self.id}, type={self.interaction_type}, search_event_id={self.search_event_id})>"
