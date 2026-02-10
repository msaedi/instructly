# backend/app/models/service_catalog.py
from __future__ import annotations

"""
Service catalog models for InstaInstru platform.

This module defines the service catalog system with four models:
1. ServiceCategory - Top-level categories (Music, Dance, Tutoring, etc.)
2. ServiceCatalog - Predefined services linked to subcategories
3. InstructorService - Links instructors to catalog services with custom pricing
4. ServiceAnalytics - Analytics and intelligence data for services

The 3-level taxonomy is: Category → Subcategory → Service
Categories derive through subcategories (no direct category_id on services).
"""

import logging
from typing import Any, Dict, List, Optional, Set, cast

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import ulid

from ..database import Base
from .types import IntegerArrayType, StringArrayType

logger = logging.getLogger(__name__)


class ServiceCategory(Base):
    """
    Model representing a top-level service category.

    Categories organize subcategories into logical groups like Music, Dance,
    Tutoring & Test Prep, etc.

    Attributes:
        id: ULID primary key
        name: Display name (e.g., "Music")
        description: Optional description of the category
        display_order: Order for UI display (lower numbers first)
        icon_name: Icon identifier for UI display
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        subcategories: List of ServiceSubcategory entries in this category
    """

    __tablename__ = "service_categories"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False)
    subtitle = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0, index=True)
    icon_name = Column(String(50), nullable=True)
    slug = Column(String(50), nullable=True)
    meta_title = Column(String(200), nullable=True)
    meta_description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    subcategories = relationship(
        "ServiceSubcategory",
        back_populates="category",
        order_by="ServiceSubcategory.display_order",
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<ServiceCategory {self.name} (id={self.id})>"

    @property
    def active_services_count(self) -> int:
        """Count of active services in this category (through subcategories)."""
        count = 0
        for sub in self.subcategories:
            count += sum(1 for entry in sub.services if entry.is_active)
        return count

    @property
    def instructor_count(self) -> int:
        """Count of unique instructors offering services in this category."""
        instructors: Set[str] = set()
        for sub in self.subcategories:
            for entry in sub.services:
                for service in entry.instructor_services:
                    if service.is_active:
                        instructors.add(service.instructor_profile_id)
        return len(instructors)

    def to_dict(
        self, include_subcategories: bool = False, include_counts: bool = False
    ) -> Dict[str, Any]:
        """Convert to dictionary for API responses.

        Args:
            include_subcategories: Include nested subcategory dicts.
            include_counts: Include active_services_count and instructor_count
                (requires eager-loaded subcategories→services→instructor_services).
        """
        data: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "display_order": self.display_order,
            "icon_name": self.icon_name,
        }
        if include_counts:
            data["active_services_count"] = self.active_services_count
            data["instructor_count"] = self.instructor_count

        if include_subcategories:
            data["subcategories"] = [
                sub.to_dict(include_services=True) for sub in self.subcategories
            ]

        return data


class ServiceCatalog(Base):
    """
    Model representing a predefined service in the catalog.

    Each catalog entry represents a standardized service that instructors
    can offer. Services belong to a subcategory (and derive their category
    through it).

    Attributes:
        id: ULID primary key
        subcategory_id: FK to service_subcategories (category derived through subcategory)
        name: Standardized service name (e.g., "Piano")
        slug: URL-friendly identifier (e.g., "piano")
        description: Default description of the service
        search_terms: Array of search keywords
        eligible_age_groups: Age groups this service is available for
        display_order: Order for UI display
        embedding: Vector embedding for semantic search
        related_services: Array of related service IDs
        online_capable: Whether this service can be offered online
        requires_certification: Whether instructors need certification
        is_active: Whether this service is available
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        subcategory: The ServiceSubcategory this belongs to
        instructor_services: List of instructors offering this service
    """

    __tablename__ = "service_catalog"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    subcategory_id = Column(
        String(26),
        ForeignKey("service_subcategories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    slug = Column(String(150), nullable=True)
    description = Column(Text, nullable=True)
    search_terms: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    eligible_age_groups: Mapped[List[str]] = mapped_column(
        StringArrayType,
        nullable=False,
        default=lambda: ["toddler", "kids", "teens", "adults"],
    )
    default_duration_minutes = Column(Integer, nullable=False, default=60)
    price_floor_in_person_cents = Column(Integer, nullable=True)
    price_floor_online_cents = Column(Integer, nullable=True)
    display_order = Column(Integer, nullable=False, default=999, index=True)
    embedding = Column(Vector(384), nullable=True)  # MiniLM (legacy)
    # OpenAI text-embedding-3-small embeddings (1536 dimensions)
    embedding_v2 = Column(Vector(1536), nullable=True)
    embedding_model = Column(Text, nullable=True)  # e.g., "text-embedding-3-small"
    embedding_model_version = Column(Text, nullable=True)  # e.g., "2024-01"
    embedding_updated_at = Column(DateTime(timezone=True), nullable=True)
    embedding_text_hash = Column(Text, nullable=True)  # Hash of text used for embedding
    related_services: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    online_capable = Column(Boolean, nullable=False, default=True, index=True)
    requires_certification = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    subcategory = relationship("ServiceSubcategory", back_populates="services")
    instructor_services = relationship(
        "InstructorService",
        back_populates="catalog_entry",
        cascade="save-update, merge",
    )

    def __repr__(self) -> str:
        """String representation."""
        status = " (inactive)" if not self.is_active else ""
        return f"<ServiceCatalog {self.name}{status}>"

    @property
    def category(self) -> Optional["ServiceCategory"]:
        """Get the parent category through subcategory."""
        if self.subcategory:
            return cast(Optional["ServiceCategory"], self.subcategory.category)
        return None

    @property
    def category_name(self) -> str:
        """Get category name through subcategory."""
        cat = self.category
        if cat:
            return cast(str, cat.name)
        return "Unknown"

    @property
    def is_offered(self) -> bool:
        """Check if any instructor currently offers this service."""
        return any(service.is_active for service in self.instructor_services)

    @property
    def instructor_count(self) -> int:
        """Count of active instructors offering this service."""
        return sum(1 for service in self.instructor_services if service.is_active)

    @property
    def price_range(self) -> tuple[Optional[float], Optional[float]]:
        """Get min and max prices from active instructors."""
        active_prices: List[float] = [
            float(service.hourly_rate) for service in self.instructor_services if service.is_active
        ]

        if not active_prices:
            return (None, None)

        return (min(active_prices), max(active_prices))

    def matches_search(self, query: str) -> bool:
        """Check if this service matches a search query."""
        query_lower = query.lower()

        # Check name
        if query_lower in self.name.lower():
            return True

        # Check description
        if self.description and query_lower in self.description.lower():
            return True

        # Check search terms
        if self.search_terms:
            for term in self.search_terms:
                if query_lower in term.lower():
                    return True

        return False

    def to_dict(self, include_instructors: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        min_price, max_price = self.price_range

        data: Dict[str, Any] = {
            "id": self.id,
            "subcategory_id": self.subcategory_id,
            "category_name": self.category_name,
            "subcategory_name": self.subcategory.name if self.subcategory else None,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "search_terms": self.search_terms,
            "eligible_age_groups": self.eligible_age_groups,
            "actual_min_price": min_price,
            "actual_max_price": max_price,
            "display_order": self.display_order,
            "related_services": self.related_services,
            "online_capable": self.online_capable,
            "requires_certification": self.requires_certification,
            "is_active": self.is_active,
            "is_offered": self.is_offered,
            "instructor_count": self.instructor_count,
        }

        if include_instructors:
            data["instructors"] = [
                {
                    "id": service.instructor_profile.user_id,
                    "first_name": service.instructor_profile.user.first_name,
                    "last_name": service.instructor_profile.user.last_name,
                    "hourly_rate": service.hourly_rate,
                    "custom_description": service.description,
                }
                for service in self.instructor_services
                if service.is_active and service.instructor_profile
            ]

        return data


class InstructorService(Base):
    """
    Model representing an instructor's offering of a catalog service.

    Links instructors to predefined catalog services with their custom
    pricing, descriptions, and filter selections.

    Attributes:
        id: ULID primary key
        instructor_profile_id: FK to instructor_profiles
        service_catalog_id: FK to service_catalog
        hourly_rate: Instructor's rate for this service
        description: Instructor's custom description
        requirements: Requirements for students
        duration_options: Available session durations in minutes
        equipment_required: Equipment needed for the service
        age_groups: Age groups the instructor works with
        filter_selections: JSONB of instructor's filter choices (e.g., {"grade_level": ["elementary"]})
        is_active: Whether currently offered (soft delete)
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        instructor_profile: The instructor offering this service
        catalog_entry: The catalog service being offered
    """

    __tablename__ = "instructor_services"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    instructor_profile_id = Column(
        String(26),
        ForeignKey("instructor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_catalog_id = Column(
        String(26),
        ForeignKey("service_catalog.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    duration_options: Mapped[List[int]] = mapped_column(
        IntegerArrayType,
        nullable=False,
        default=lambda: [60],
    )
    equipment_required: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    age_groups: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    filter_selections = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    offers_travel = Column(Boolean, nullable=False, default=False)
    offers_at_location = Column(Boolean, nullable=False, default=False)
    offers_online = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    instructor_profile = relationship("InstructorProfile", back_populates="instructor_services")
    catalog_entry = relationship("ServiceCatalog", back_populates="instructor_services")

    def __init__(self, **kwargs: Any) -> None:
        """Initialize service with logging."""
        super().__init__(**kwargs)
        logger.debug(
            f"Creating instructor service for catalog {kwargs.get('service_catalog_id')} "
            f"and instructor {kwargs.get('instructor_profile_id')}"
        )

    def __repr__(self) -> str:
        """String representation."""
        status = " (inactive)" if not self.is_active else ""
        catalog_name = self.catalog_entry.name if self.catalog_entry else "Unknown"
        return f"<InstructorService {catalog_name} ${self.hourly_rate}/hr{status}>"

    @property
    def name(self) -> str:
        """Get service name from catalog entry."""
        entry = self.catalog_entry
        name_value = getattr(entry, "name", None)
        if isinstance(name_value, str):
            return name_value
        return "Unknown Service"

    @property
    def category(self) -> str:
        """Get category name from catalog entry (through subcategory)."""
        entry = self.catalog_entry
        if entry:
            cat = entry.category
            if cat:
                return cast(str, cat.name)
        return "Unknown"

    @property
    def category_slug(self) -> str:
        """Get category slug for URL construction."""
        entry = self.catalog_entry
        if entry:
            cat = entry.category
            slug = getattr(cat, "slug", None)
            if isinstance(slug, str) and slug.strip():
                return slug
        return "unknown"

    def session_price(self, duration_minutes: int) -> float:
        """
        Calculate the price for a session of given duration.

        Args:
            duration_minutes: Duration of the session in minutes

        Returns:
            float: Price for the session
        """
        hourly_rate = float(self.hourly_rate)
        return (hourly_rate * duration_minutes) / 60.0

    def deactivate(self) -> None:
        """
        Soft delete this service by marking it as inactive.

        Preserves the record for historical bookings while removing
        it from active service listings.
        """
        self.is_active = False
        catalog_name = self.catalog_entry.name if self.catalog_entry else "Unknown"
        logger.info(f"Deactivated instructor service {self.id}: {catalog_name}")

    def activate(self) -> None:
        """
        Reactivate a previously deactivated service.

        Makes the service available for booking again.
        """
        self.is_active = True
        catalog_name = self.catalog_entry.name if self.catalog_entry else "Unknown"
        logger.info(f"Activated instructor service {self.id}: {catalog_name}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "instructor_profile_id": self.instructor_profile_id,
            "service_catalog_id": self.service_catalog_id,
            "name": self.catalog_entry.name if self.catalog_entry else "Unknown Service",
            "category": self.category,
            "hourly_rate": self.hourly_rate,
            "description": self.description
            or (self.catalog_entry.description if self.catalog_entry else None),
            "requirements": self.requirements,
            "duration_options": self.duration_options,
            "equipment_required": self.equipment_required,
            "age_groups": self.age_groups,
            "filter_selections": self.filter_selections,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ServiceAnalytics(Base):
    """
    Model representing analytics and intelligence data for services.

    This table stores calculated metrics, demand signals, and pricing intelligence
    for each service in the catalog. Data is periodically updated from usage patterns.
    """

    __tablename__ = "service_analytics"

    service_catalog_id = Column(
        String(26),
        ForeignKey("service_catalog.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    search_count_7d = Column(Integer, nullable=False, default=0, index=True)
    search_count_30d = Column(Integer, nullable=False, default=0)
    booking_count_7d = Column(Integer, nullable=False, default=0)
    booking_count_30d = Column(Integer, nullable=False, default=0, index=True)
    search_to_view_rate = Column(Float, nullable=True)
    view_to_booking_rate = Column(Float, nullable=True)
    avg_price_booked = Column(Float, nullable=True)
    price_percentile_25 = Column(Float, nullable=True)
    price_percentile_50 = Column(Float, nullable=True)
    price_percentile_75 = Column(Float, nullable=True)
    most_booked_duration = Column(Integer, nullable=True)
    duration_distribution = Column(Text, nullable=True)  # JSON stored as text
    peak_hours = Column(Text, nullable=True)  # JSON stored as text
    peak_days = Column(Text, nullable=True)  # JSON stored as text
    seasonality_index = Column(Text, nullable=True)  # JSON stored as text
    avg_rating = Column(Float, nullable=True)
    completion_rate = Column(Float, nullable=True)
    active_instructors = Column(Integer, nullable=False, default=0)
    total_weekly_hours = Column(Float, nullable=True)
    supply_demand_ratio = Column(Float, nullable=True)
    last_calculated = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    catalog_entry = relationship("ServiceCatalog", backref="analytics", uselist=False)

    def __repr__(self) -> str:
        """String representation."""
        return f"<ServiceAnalytics service_id={self.service_catalog_id} searches_7d={self.search_count_7d}>"

    @property
    def demand_score(self) -> float:
        """Calculate a demand score from 0-100."""
        if not self.search_count_30d:
            return 0.0

        # Weighted combination of metrics
        search_count_30d = cast(int, self.search_count_30d)
        booking_count_30d = cast(int, self.booking_count_30d)
        view_to_booking_rate = cast(Optional[float], self.view_to_booking_rate)

        search_weight = min(search_count_30d / 100, 1.0) * 40
        booking_weight = min(booking_count_30d / 20, 1.0) * 40
        conversion_weight = (view_to_booking_rate or 0.0) * 20

        return search_weight + booking_weight + conversion_weight

    @property
    def is_trending(self) -> bool:
        """Check if service is trending upward."""
        if not self.search_count_30d or not self.search_count_7d:
            return False

        # If 7-day average is 20% higher than 30-day average
        search_count_7d = cast(int, self.search_count_7d)
        search_count_30d = cast(int, self.search_count_30d)
        avg_7d = search_count_7d / 7
        avg_30d = search_count_30d / 30

        return avg_7d > avg_30d * 1.2

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "service_catalog_id": self.service_catalog_id,
            "search_count_7d": self.search_count_7d,
            "search_count_30d": self.search_count_30d,
            "booking_count_7d": self.booking_count_7d,
            "booking_count_30d": self.booking_count_30d,
            "search_to_view_rate": self.search_to_view_rate,
            "view_to_booking_rate": self.view_to_booking_rate,
            "avg_price_booked": self.avg_price_booked,
            "price_percentiles": {
                "p25": self.price_percentile_25,
                "p50": self.price_percentile_50,
                "p75": self.price_percentile_75,
            },
            "most_booked_duration": self.most_booked_duration,
            "avg_rating": self.avg_rating,
            "completion_rate": self.completion_rate,
            "active_instructors": self.active_instructors,
            "total_weekly_hours": self.total_weekly_hours,
            "supply_demand_ratio": self.supply_demand_ratio,
            "demand_score": self.demand_score,
            "is_trending": self.is_trending,
            "last_calculated": self.last_calculated.isoformat() if self.last_calculated else None,
        }
