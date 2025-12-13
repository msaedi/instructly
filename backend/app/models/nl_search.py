# backend/app/models/nl_search.py
"""
Natural Language Search models for InstaInstru platform.

This module defines models for NL search analytics, conversion tracking,
and reference data tables.

Tables:
- SearchQuery: Analytics for NL search queries with parsing metrics
- SearchClick: Conversion tracking for search result interactions
- NYCLocation: Reference data for NYC boroughs and neighborhoods
- PriceThreshold: Configuration for price intent mapping by category
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base
from .types import StringArrayType

# Cross-database compatible JSON type
json_type = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class SearchQuery(Base):
    """
    Model representing an NL search query for analytics.

    Tracks search queries with parsing mode, latency metrics, and results
    for analysis and optimization of the search system.

    Attributes:
        id: Primary key (ULID)
        original_query: The raw query text from the user
        normalized_query: Parsed/normalized query as JSONB
        parsing_mode: How the query was parsed ('regex', 'llm', 'hybrid')
        parsing_latency_ms: Time to parse the query in milliseconds
        result_count: Number of results returned
        top_result_ids: Array of top result service IDs
        user_id: Optional user who made the search
        session_id: Session identifier for anonymous users
        total_latency_ms: Total search time in milliseconds
        cache_hit: Whether results came from cache
        degraded: Whether search ran in degraded mode
        created_at: Timestamp of the search
    """

    __tablename__ = "search_queries"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    original_query = Column(Text, nullable=False)
    normalized_query = Column(json_type, nullable=False)
    parsing_mode = Column(Text, nullable=False)  # 'regex', 'llm', 'hybrid'
    parsing_latency_ms = Column(Integer, nullable=False)
    result_count = Column(Integer, nullable=False)
    top_result_ids: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    user_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id = Column(Text, nullable=True)
    total_latency_ms = Column(Integer, nullable=False)
    cache_hit = Column(Boolean, nullable=False, default=False, server_default="false")
    degraded = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    clicks = relationship(
        "SearchClick", back_populates="search_query", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SearchQuery '{self.original_query[:30]}...' results={self.result_count}>"


class SearchClick(Base):
    """
    Model representing a click/action on a search result.

    Tracks conversion events from search results to help optimize
    ranking and understand user behavior.

    Attributes:
        id: Primary key (ULID)
        search_query_id: Foreign key to the search query
        service_id: The service that was clicked
        instructor_id: The instructor associated with the result
        position: Rank position in search results (1-indexed)
        action: Type of action ('view', 'book', 'message', 'favorite')
        created_at: Timestamp of the action
    """

    __tablename__ = "search_clicks"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    search_query_id = Column(
        String(26),
        ForeignKey("search_queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id = Column(
        String(26),
        ForeignKey("service_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    instructor_id = Column(
        String(26),
        ForeignKey("instructor_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    position = Column(Integer, nullable=False)  # 1-indexed position in results
    action = Column(Text, nullable=False)  # 'view', 'book', 'message', 'favorite'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    search_query = relationship("SearchQuery", back_populates="clicks")
    service = relationship("ServiceCatalog", foreign_keys=[service_id])
    instructor = relationship("InstructorProfile", foreign_keys=[instructor_id])

    def __repr__(self) -> str:
        return f"<SearchClick action={self.action} pos={self.position}>"


class NYCLocation(Base):
    """
    Reference data for NYC boroughs and neighborhoods.

    Used for location parsing and geocoding in NL search queries.
    Seeded with boroughs and key neighborhoods.

    Attributes:
        id: Primary key (e.g., 'loc_manhattan')
        name: Display name (e.g., 'Manhattan')
        type: Location type ('borough' or 'neighborhood')
        borough: Parent borough name
        aliases: Array of alternative names/abbreviations
        lat: Latitude of centroid
        lng: Longitude of centroid
    """

    __tablename__ = "nyc_locations"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    type = Column(Text, nullable=False)  # 'borough', 'neighborhood'
    borough = Column(Text, nullable=False)
    aliases: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<NYCLocation {self.name} ({self.type})>"

    @property
    def all_names(self) -> List[str]:
        """Get all names including aliases for matching."""
        names = [self.name.lower()]
        if self.aliases:
            names.extend(alias.lower() for alias in self.aliases)
        return names


class PriceThreshold(Base):
    """
    Configuration for mapping price intents to max prices by category.

    Used to interpret queries like "affordable piano lessons" where
    "affordable" maps to a category-specific price threshold.

    Attributes:
        id: Primary key (e.g., 'pt_music_budget')
        category: Service category ('music', 'tutoring', 'sports', 'language', 'general')
        intent: Price intent keyword ('budget', 'standard', 'premium')
        max_price: Maximum hourly rate for this intent/category combination
    """

    __tablename__ = "price_thresholds"

    id = Column(Text, primary_key=True)
    category = Column(Text, nullable=False)  # 'music', 'tutoring', 'sports', 'language', 'general'
    intent = Column(Text, nullable=False)  # 'budget', 'standard', 'premium'
    max_price = Column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<PriceThreshold {self.category}/{self.intent} max=${self.max_price}>"

    @classmethod
    def get_max_price(
        cls,
        category: str,
        intent: str,
        default: Optional[int] = None,
    ) -> Optional[int]:
        """
        Get max price for a category/intent combination.

        Note: This is a helper method signature. Actual implementation
        should use a repository pattern with database session.

        Args:
            category: Service category
            intent: Price intent
            default: Default value if not found

        Returns:
            Max price or default
        """
        # This is just a signature - actual lookup should be in repository
        return default
