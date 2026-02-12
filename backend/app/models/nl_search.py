# backend/app/models/nl_search.py
"""
Natural Language Search models for InstaInstru platform.

This module defines models for NL search analytics, conversion tracking,
and reference data tables.

Tables:
- SearchQuery: Analytics for NL search queries with parsing metrics
- SearchClick: Conversion tracking for search result interactions
- RegionSettings: Per-region configuration (pricing, timezone, etc.)
- PriceThreshold: Configuration for price intent mapping by category and region
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base

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
        user_id: Optional user who made the search
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
    user_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    total_latency_ms = Column(Integer, nullable=False)
    cache_hit = Column(Boolean, nullable=False, default=False, server_default="false")
    degraded = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "parsing_mode IN ('regex', 'llm', 'hybrid')",
            name="ck_search_queries_parsing_mode",
        ),
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

    __table_args__ = (
        CheckConstraint(
            "action IN ('view', 'book', 'message', 'favorite')",
            name="ck_search_clicks_action",
        ),
    )

    # Relationships
    search_query = relationship("SearchQuery", back_populates="clicks")
    service = relationship("ServiceCatalog", foreign_keys=[service_id])
    instructor = relationship("InstructorProfile", foreign_keys=[instructor_id])

    def __repr__(self) -> str:
        return f"<SearchClick action={self.action} pos={self.position}>"


class RegionSettings(Base):
    """
    Per-region configuration for multi-city support.

    Stores region-specific settings including pricing floors,
    timezone, and platform fees.

    Attributes:
        id: Primary key (ULID)
        region_code: Unique region identifier ('nyc', 'chicago', etc.)
        region_name: Display name ('New York City', 'Chicago', etc.)
        country_code: Country code ('us', 'ca', etc.)
        timezone: IANA timezone string
        price_floor_in_person: Minimum hourly rate for in-person lessons
        price_floor_remote: Minimum hourly rate for remote lessons
        currency_code: Currency code ('USD', 'CAD', etc.)
        student_fee_percent: Platform fee charged to students
        is_active: Whether this region is active on the platform
        launch_date: Planned or actual launch date
    """

    __tablename__ = "region_settings"

    id = Column(Text, primary_key=True, default=lambda: str(ulid.ULID()))
    region_code = Column(Text, unique=True, nullable=False)
    region_name = Column(Text, nullable=False)
    country_code = Column(Text, nullable=False, default="us")
    timezone = Column(Text, nullable=False)
    price_floor_in_person = Column(Integer, nullable=False)
    price_floor_remote = Column(Integer, nullable=False)
    currency_code = Column(Text, nullable=False, default="USD")
    student_fee_percent = Column(Numeric(5, 2), nullable=False, default=Decimal("12.0"))
    is_active = Column(Boolean, nullable=False, default=False, server_default="false")
    launch_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return f"<RegionSettings {self.region_code} ({status})>"


class PriceThreshold(Base):
    """
    Configuration for mapping price intents to max prices by category and region.

    Used to interpret queries like "affordable piano lessons" where
    "affordable" maps to a category-specific, region-specific price threshold.

    Attributes:
        id: Primary key (e.g., 'pt_nyc_music_budget')
        region_code: Region identifier ('nyc', 'global' for fallback)
        category: Service category ('music', 'tutoring', 'sports', 'language', 'general')
        intent: Price intent keyword ('budget', 'standard', 'premium')
        max_price: Maximum hourly rate for this intent (for budget/standard)
        min_price: Minimum hourly rate for this intent (for premium)
    """

    __tablename__ = "price_thresholds"

    id = Column(Text, primary_key=True)
    region_code = Column(Text, nullable=False, default="nyc")
    category = Column(Text, nullable=False)  # 'music', 'tutoring', 'sports', 'language', 'general'
    intent = Column(Text, nullable=False)  # 'budget', 'standard', 'premium'
    max_price = Column(Integer, nullable=True)  # For budget/standard intents
    min_price = Column(Integer, nullable=True)  # For premium intent
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        price_info = f"max=${self.max_price}" if self.max_price else f"min=${self.min_price}"
        return f"<PriceThreshold {self.region_code}/{self.category}/{self.intent} {price_info}>"

    @classmethod
    def get_max_price(
        cls,
        category: str,
        intent: str,
        default: Optional[int] = None,
        region_code: str = "nyc",
    ) -> Optional[int]:
        """
        Get max price for a category/intent combination.

        Note: This is a helper method signature. Actual implementation
        should use a repository pattern with database session.

        Args:
            category: Service category
            intent: Price intent
            default: Default value if not found
            region_code: Region to lookup thresholds for

        Returns:
            Max price or default
        """
        # This is just a signature - actual lookup should be in repository
        return default
