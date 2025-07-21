# backend/app/models/service_catalog.py
"""
Service catalog models for InstaInstru platform.

This module defines the service catalog system with three models:
1. ServiceCategory - Categories like Music, Academic, Fitness
2. ServiceCatalog - Predefined services with standardized names
3. InstructorService - Links instructors to catalog services with custom pricing
"""

import logging
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .types import IntegerArrayType, StringArrayType

if TYPE_CHECKING:
    pass

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
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        catalog_entries: List of ServiceCatalog entries in this category
    """

    __tablename__ = "service_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    catalog_entries = relationship(
        "ServiceCatalog",
        back_populates="category",
        order_by="ServiceCatalog.name",
    )

    def __repr__(self):
        """String representation."""
        return f"<ServiceCategory {self.name} ({self.slug})>"

    @property
    def active_services_count(self) -> int:
        """Count of active services in this category."""
        return sum(1 for entry in self.catalog_entries if entry.is_active)

    @property
    def instructor_count(self) -> int:
        """Count of unique instructors offering services in this category."""
        instructors = set()
        for entry in self.catalog_entries:
            for service in entry.instructor_services:
                if service.is_active:
                    instructors.add(service.instructor_profile_id)
        return len(instructors)

    def to_dict(self, include_services: bool = False) -> dict:
        """Convert to dictionary for API responses."""
        data = {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "display_order": self.display_order,
            "active_services_count": self.active_services_count,
            "instructor_count": self.instructor_count,
        }

        if include_services:
            data["services"] = [entry.to_dict() for entry in self.catalog_entries if entry.is_active]

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
        typical_duration_options: Common duration options in minutes
        min_recommended_price: Minimum suggested hourly rate
        max_recommended_price: Maximum suggested hourly rate
        is_active: Whether this service is available
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        category: The ServiceCategory this belongs to
        instructor_services: List of instructors offering this service
    """

    __tablename__ = "service_catalog"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("service_categories.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    search_terms: Mapped[List[str]] = mapped_column(StringArrayType, nullable=True)
    typical_duration_options: Mapped[List[int]] = mapped_column(IntegerArrayType, nullable=False, default=[60])
    min_recommended_price = Column(Float, nullable=True)
    max_recommended_price = Column(Float, nullable=True)
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

    def __repr__(self):
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
        active_prices = [service.hourly_rate for service in self.instructor_services if service.is_active]

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

    def to_dict(self, include_instructors: bool = False) -> dict:
        """Convert to dictionary for API responses."""
        min_price, max_price = self.price_range

        data = {
            "id": self.id,
            "category_id": self.category_id,
            "category_name": self.category.name,
            "category_slug": self.category.slug,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "search_terms": self.search_terms,
            "typical_duration_options": self.typical_duration_options,
            "min_recommended_price": self.min_recommended_price,
            "max_recommended_price": self.max_recommended_price,
            "actual_min_price": min_price,
            "actual_max_price": max_price,
            "is_active": self.is_active,
            "is_offered": self.is_offered,
            "instructor_count": self.instructor_count,
        }

        if include_instructors:
            data["instructors"] = [
                {
                    "id": service.instructor_profile.user_id,
                    "name": service.instructor_profile.user.full_name,
                    "hourly_rate": service.hourly_rate,
                    "custom_description": service.description,
                }
                for service in self.instructor_services
                if service.is_active
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
        description: Instructor's custom description (optional)
        duration_options: Available session durations in minutes
        is_active: Whether currently offered (soft delete)
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        instructor_profile: The instructor offering this service
        catalog_entry: The catalog service being offered
    """

    __tablename__ = "instructor_services"

    id = Column(Integer, primary_key=True, index=True)
    instructor_profile_id = Column(
        Integer, ForeignKey("instructor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_catalog_id = Column(
        Integer, ForeignKey("service_catalog.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    hourly_rate = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    duration_options: Mapped[List[int]] = mapped_column(IntegerArrayType, nullable=False, default=[60])
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    instructor_profile = relationship("InstructorProfile", back_populates="instructor_services")
    catalog_entry = relationship("ServiceCatalog", back_populates="instructor_services")

    def __init__(self, **kwargs):
        """Initialize service with logging."""
        super().__init__(**kwargs)
        logger.debug(
            f"Creating instructor service for catalog {kwargs.get('service_catalog_id')} "
            f"and instructor {kwargs.get('instructor_profile_id')}"
        )

    def __repr__(self):
        """String representation."""
        status = " (inactive)" if not self.is_active else ""
        catalog_name = self.catalog_entry.name if self.catalog_entry else "Unknown"
        return f"<InstructorService {catalog_name} ${self.hourly_rate}/hr{status}>"

    @property
    def name(self) -> str:
        """Get service name from catalog entry."""
        return self.catalog_entry.name if self.catalog_entry else "Unknown Service"

    @property
    def category(self) -> str:
        """Get category name from catalog entry."""
        return self.catalog_entry.category.name if self.catalog_entry and self.catalog_entry.category else "Unknown"

    @property
    def category_slug(self) -> str:
        """Get category slug from catalog entry."""
        return self.catalog_entry.category.slug if self.catalog_entry and self.catalog_entry.category else "unknown"

    def session_price(self, duration_minutes: int) -> float:
        """
        Calculate the price for a session of given duration.

        Args:
            duration_minutes: Duration of the session in minutes

        Returns:
            float: Price for the session
        """
        return (self.hourly_rate * duration_minutes) / 60.0

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

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "instructor_profile_id": self.instructor_profile_id,
            "service_catalog_id": self.service_catalog_id,
            "name": self.catalog_entry.name if self.catalog_entry else "Unknown Service",
            "category": self.category,
            "category_slug": self.category_slug,
            "hourly_rate": self.hourly_rate,
            "description": self.description or (self.catalog_entry.description if self.catalog_entry else None),
            "duration_options": self.duration_options,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
