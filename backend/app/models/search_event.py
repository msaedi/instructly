# backend/app/models/search_event.py
"""
Search Event Model for analytics tracking.

This model stores every search event for analytics purposes,
maintaining a complete history of all searches without deduplication.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base


class SearchEvent(Base):
    """
    Append-only event log for search analytics.

    Unlike SearchHistory which deduplicates for UX, this table
    records every single search event for analytics and tracking.
    """

    __tablename__ = "search_events"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # User identification (one or the other)
    user_id = Column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
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
    searched_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    session_id = Column(
        String(36), nullable=True, index=True, comment="Browser session for journey tracking"
    )
    referrer = Column(String(255), nullable=True, comment="Page where search originated")

    # Additional context as JSON
    search_context = Column(
        JSON, nullable=True, comment="Additional context: filters, location, device info, etc."
    )

    # Enhanced analytics columns
    ip_address = Column(String(45), nullable=True, comment="IPv4 or IPv6 address")
    ip_address_hash = Column(String(64), nullable=True, comment="SHA-256 hash of IP for privacy")
    geo_data = Column(
        JSON, nullable=True, comment="Geolocation data: country, state, city, borough, postal_code"
    )
    device_type = Column(String(20), nullable=True, comment="desktop, mobile, tablet")
    browser_info = Column(JSON, nullable=True, comment="Browser name, version, OS")
    connection_type = Column(String(20), nullable=True, comment="wifi, cellular, ethernet")
    page_view_count = Column(Integer, nullable=True, comment="Pages viewed in session")
    session_duration = Column(Integer, nullable=True, comment="Session duration in seconds")
    is_returning_user = Column(Boolean, nullable=True, default=False)

    # Privacy and consent
    consent_given = Column(Boolean, nullable=True, default=True)
    consent_type = Column(
        String(50), nullable=True, comment="Type of consent: analytics, marketing, etc."
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    candidates = relationship(
        "SearchEventCandidate",
        back_populates="search_event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<SearchEvent(id={self.id}, query='{self.search_query[:30]}...', user_id={self.user_id})>"


class SearchEventCandidate(Base):
    """
    Top-N candidate considered for a search event.

    Stores ranking position and scores for observability/analytics.
    """

    __tablename__ = "search_event_candidates"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    search_event_id = Column(
        String(26), ForeignKey("search_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = Column(SmallInteger, nullable=False, comment="1-based rank in candidate list")
    service_catalog_id = Column(
        String(26), ForeignKey("service_catalog.id", ondelete="SET NULL"), nullable=True, index=True
    )
    score = Column(Float, nullable=True, comment="primary score used for ordering (e.g., hybrid)")
    vector_score = Column(Float, nullable=True, comment="raw vector similarity if available")
    lexical_score = Column(
        Float, nullable=True, comment="text/trigram or token overlap score if available"
    )
    source = Column(String(20), nullable=True, comment="vector|trgm|exact|hybrid")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    search_event = relationship("SearchEvent", back_populates="candidates")
