# backend/app/models/service_catalog.py
from __future__ import annotations

"""
Service catalog models for InstaInstru platform.

This module defines the service catalog system with three models:
1. ServiceCategory - Categories like Music, Academic, Fitness
2. ServiceCatalog - Predefined services with standardized names
3. InstructorService - Links instructors to catalog services with custom pricing
"""

import logging
from typing import Any, Dict, List, Optional, Set, cast

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
import ulid

from ..database import Base
from .types import IntegerArrayType, StringArrayType

logger = logging.getLogger(__name__)


class ServiceCategory(Base):
    """
    Model representing a service category.

    Categories organize services into logical groups like Music, Academic,
    Fitness, etc. Each category has a unique slug for URL-friendly identifiers.

    Attributes:
        id: Primary key
        name: Display name (e.g., "Music & Arts")
        slug: URL-friendly identifier (e.g., "music-arts")
        description: Optional description of the category
        display_order: Order for UI display (lower numbers first)
        icon_name: Icon identifier for UI display
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        catalog_entries: List of ServiceCatalog entries in this category
    """

    __tablename__ = "service_categories"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    name = Column(String, nullable=False)
    subtitle = Column(String(100), nullable=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0, index=True)
    icon_name = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    catalog_entries = relationship(
        "ServiceCatalog",
        back_populates="category",
        order_by="ServiceCatalog.name",
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<ServiceCategory {self.name} ({self.slug})>"

    @property
    def active_services_count(self) -> int:
        """Count of active services in this category."""
        return sum(1 for entry in self.catalog_entries if entry.is_active)

    @property
    def instructor_count(self) -> int:
        """Count of unique instructors offering services in this category."""
        instructors: Set[str] = set()
        for entry in self.catalog_entries:
            for service in entry.instructor_services:
                if service.is_active:
                    instructors.add(service.instructor_profile_id)
        return len(instructors)

    def to_dict(self, include_services: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        data: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "display_order": self.display_order,
            "icon_name": self.icon_name,
            "active_services_count": self.active_services_count,
            "instructor_count": self.instructor_count,
        }

        if include_services:
            data["services"] = [
                entry.to_dict() for entry in self.catalog_entries if entry.is_active
            ]

        return data


class ServiceCatalog(Base):
    """
    Model representing a predefined service in the catalog.

    Each catalog entry represents a standardized service that instructors
    can offer. This ensures consistency in naming and helps with search
    and filtering.

    Attributes:
        id: Primary key
        category_id: Foreign key to service_categories
        name: Standardized service name (e.g., "Piano Lessons")
        slug: URL-friendly identifier (e.g., "piano-lessons")
        description: Default description of the service
        search_terms: Array of search keywords
        display_order: Order for UI display (lower numbers first)
        embedding: Vector embedding for semantic search
        related_services: Array of related service IDs
        online_capable: Whether this service can be offered online
        requires_certification: Whether instructors need certification
        is_active: Whether this service is available
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        category: The ServiceCategory this belongs to
        instructor_services: List of instructors offering this service
    """

    __tablename__ = "service_catalog"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    category_id = Column(
        String(26), ForeignKey("service_categories.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    search_terms: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    display_order = Column(Integer, nullable=False, default=999, index=True)
    embedding = Column(Vector(384), nullable=True)
    related_services: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    online_capable = Column(Boolean, nullable=False, default=True, index=True)
    requires_certification = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category = relationship("ServiceCategory", back_populates="catalog_entries")
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
            cast(float, service.hourly_rate)
            for service in self.instructor_services
            if service.is_active
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
            "category_id": self.category_id,
            "category_name": self.category.name,
            "category_slug": self.category.slug,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "search_terms": self.search_terms,
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

    This replaces the old Service model and links instructors to predefined
    catalog services with their custom pricing and descriptions.

    Attributes:
        id: Primary key
        instructor_profile_id: Foreign key to instructor_profiles
        service_catalog_id: Foreign key to service_catalog
        hourly_rate: Instructor's rate for this service
        experience_level: Level of experience (beginner, intermediate, advanced)
        description: Instructor's custom description (optional)
        requirements: Requirements for students
        duration_options: Available session durations in minutes
        equipment_required: Equipment needed for the service
        levels_taught: Skill levels the instructor teaches
        age_groups: Age groups the instructor works with
        location_types: Types of locations offered (in-person, online)
        max_distance_miles: Maximum travel distance for in-person sessions
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
    hourly_rate = Column(Float, nullable=False)
    experience_level = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    duration_options: Mapped[List[int]] = mapped_column(
        IntegerArrayType, nullable=False, default=[60]
    )
    equipment_required: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    levels_taught: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    age_groups: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    location_types: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    max_distance_miles = Column(Integer, nullable=True)
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
        """Get category name from catalog entry."""
        entry = self.catalog_entry
        category = getattr(entry, "category", None)
        name_value = getattr(category, "name", None)
        if isinstance(name_value, str):
            return name_value
        return "Unknown"

    @property
    def category_slug(self) -> str:
        """Get category slug from catalog entry."""
        entry = self.catalog_entry
        category = getattr(entry, "category", None)
        slug_value = getattr(category, "slug", None)
        if isinstance(slug_value, str):
            return slug_value
        return "unknown"

    def session_price(self, duration_minutes: int) -> float:
        """
        Calculate the price for a session of given duration.

        Args:
            duration_minutes: Duration of the session in minutes

        Returns:
            float: Price for the session
        """
        hourly_rate = cast(float, self.hourly_rate)
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
            "category_slug": self.category_slug,
            "hourly_rate": self.hourly_rate,
            "experience_level": self.experience_level,
            "description": self.description
            or (self.catalog_entry.description if self.catalog_entry else None),
            "requirements": self.requirements,
            "duration_options": self.duration_options,
            "equipment_required": self.equipment_required,
            "levels_taught": self.levels_taught,
            "age_groups": self.age_groups,
            "location_types": self.location_types,
            "max_distance_miles": self.max_distance_miles,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ServiceAnalytics(Base):
    """
    Model representing analytics and intelligence data for services.

    This table stores calculated metrics, demand signals, and pricing intelligence
    for each service in the catalog. Data is periodically updated from usage patterns.

    Attributes:
        service_catalog_id: Primary key and foreign key to service_catalog
        search_count_7d: Number of searches in last 7 days
        search_count_30d: Number of searches in last 30 days
        booking_count_7d: Number of bookings in last 7 days
        booking_count_30d: Number of bookings in last 30 days
        search_to_view_rate: Conversion rate from search to view
        view_to_booking_rate: Conversion rate from view to booking
        avg_price_booked: Average price of completed bookings
        price_percentile_25: 25th percentile of booking prices
        price_percentile_50: Median booking price
        price_percentile_75: 75th percentile of booking prices
        most_booked_duration: Most popular session duration
        duration_distribution: JSON of duration booking counts
        peak_hours: JSON of busiest hours
        peak_days: JSON of busiest days
        seasonality_index: JSON of seasonal demand patterns
        avg_rating: Average instructor rating for this service
        completion_rate: Percentage of bookings completed
        active_instructors: Number of active instructors
        total_weekly_hours: Total hours available per week
        supply_demand_ratio: Ratio of supply to demand
        last_calculated: When analytics were last updated

    Relationships:
        catalog_entry: The service catalog entry
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
