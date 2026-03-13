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

from decimal import Decimal
import logging
from typing import Any, Callable, Dict, List, Optional, Set, TypedDict, cast

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
import ulid

from ..core.exceptions import BusinessRuleException
from ..database import Base
from .types import IntegerArrayType, StringArrayType

logger = logging.getLogger(__name__)

SERVICE_FORMAT_STUDENT_LOCATION = "student_location"
SERVICE_FORMAT_INSTRUCTOR_LOCATION = "instructor_location"
SERVICE_FORMAT_ONLINE = "online"
SERVICE_PRICE_FORMAT_ORDER = (
    SERVICE_FORMAT_STUDENT_LOCATION,
    SERVICE_FORMAT_INSTRUCTOR_LOCATION,
    SERVICE_FORMAT_ONLINE,
)
BOOKING_TO_SERVICE_FORMAT = {
    "student_location": SERVICE_FORMAT_STUDENT_LOCATION,
    "instructor_location": SERVICE_FORMAT_INSTRUCTOR_LOCATION,
    "online": SERVICE_FORMAT_ONLINE,
    "neutral_location": SERVICE_FORMAT_INSTRUCTOR_LOCATION,
}
PRICE_QUANTUM = Decimal("0.01")


class SerializedFormatPrice(TypedDict):
    format: str
    hourly_rate: Decimal


class ServiceCategory(Base):
    """
    Model representing a top-level service category.

    Categories organize subcategories into logical groups like Music, Dance,
    Tutoring & Test Prep, etc.

    Attributes:
        id: ULID primary key
        name: Display name (e.g., "Music")
        subtitle: Short tagline shown below the category name
        slug: URL-friendly identifier for routing
        description: Optional description of the category
        display_order: Order for UI display (lower numbers first)
        icon_name: Icon identifier for UI display
        meta_title: SEO page title override
        meta_description: SEO meta description override
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
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

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
        embedding_v2: Vector embedding for semantic search
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
        default=lambda: ["kids", "teens", "adults"],
    )
    default_duration_minutes = Column(Integer, nullable=False, default=60)
    price_floor_in_person_cents = Column(Integer, nullable=True)
    price_floor_online_cents = Column(Integer, nullable=True)
    display_order = Column(Integer, nullable=False, default=999, index=True)
    # OpenAI text-embedding-3-small embeddings (1536 dimensions)
    embedding_v2 = Column(Vector(1536), nullable=True)
    embedding_model = Column(Text, nullable=True)  # e.g., "text-embedding-3-small"
    embedding_model_version = Column(Text, nullable=True)  # e.g., "2024-01"
    embedding_updated_at = Column(DateTime(timezone=True), nullable=True)
    embedding_text_hash = Column(Text, nullable=True)  # Hash of text used for embedding
    online_capable = Column(Boolean, nullable=False, default=True, index=True)
    requires_certification = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

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
            float(service.min_hourly_rate)
            for service in self.instructor_services
            if service.is_active and service.min_hourly_rate is not None
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
                    "min_hourly_rate": service.min_hourly_rate,
                    "format_prices": service.serialized_format_prices,
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
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "ix_instructor_services_profile_active",
            "instructor_profile_id",
            "is_active",
        ),
    )

    # Relationships
    instructor_profile = relationship("InstructorProfile", back_populates="instructor_services")
    catalog_entry = relationship("ServiceCatalog", back_populates="instructor_services")
    # IMPORTANT: Always eager-load this relationship when accessing pricing
    # properties (min_hourly_rate, offers_*, prices_by_format, serialized_format_prices).
    # All repository methods that return InstructorService include
    # joinedload(InstructorService.format_prices).
    format_prices = relationship(
        "ServiceFormatPrice",
        back_populates="service",
        cascade="all, delete-orphan",
        order_by="ServiceFormatPrice.created_at",
    )

    @staticmethod
    def _coerce_decimal_rate(value: Any) -> Decimal:
        """Normalize arbitrary numeric input to a two-decimal hourly rate."""
        return Decimal(str(value)).quantize(PRICE_QUANTUM)

    @cast(Callable[..., Callable[..., Any]], validates)("format_prices")
    def _coerce_format_price_row(self, _key: str, price_row: Any) -> "ServiceFormatPrice":
        """Accept dict-style relationship rows while keeping child models canonical."""
        if isinstance(price_row, ServiceFormatPrice):
            if price_row.hourly_rate is not None:
                price_row.hourly_rate = self._coerce_decimal_rate(price_row.hourly_rate)
            return price_row

        if isinstance(price_row, dict):
            hourly_rate = price_row.get("hourly_rate")
            if hourly_rate is None:
                raise ValueError("format_prices entries must include hourly_rate")
            fmt = str(price_row.get("format", ""))
            if not fmt:
                raise ValueError(
                    f"format_prices entries must have a non-empty format "
                    f"(valid: {', '.join(SERVICE_PRICE_FORMAT_ORDER)})"
                )
            return ServiceFormatPrice(
                format=fmt,
                hourly_rate=self._coerce_decimal_rate(hourly_rate),
            )

        raise TypeError("format_prices entries must be ServiceFormatPrice or dict")

    def __repr__(self) -> str:
        """String representation."""
        status = " (inactive)" if not self.is_active else ""
        catalog_name = self.catalog_entry.name if self.catalog_entry else "Unknown"
        headline_rate = self.min_hourly_rate
        if headline_rate is None:
            return f"<InstructorService {catalog_name} no-pricing{status}>"
        return f"<InstructorService {catalog_name} ${headline_rate}/hr{status}>"

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

    @property
    def prices_by_format(self) -> Dict[str, Decimal]:
        """Return a format->hourly_rate mapping for active pricing rows.

        Cached per instance to avoid recomputation across multiple property
        accesses (min_hourly_rate, offers_*, session_price, etc.).
        Invalidated by _invalidate_price_cache() after sync_format_prices.
        """
        cache: dict[str, Decimal] | None = getattr(self, "_prices_by_format_cache", None)
        if cache is not None:
            return cache
        price_rows = getattr(self, "format_prices", None) or []
        result: dict[str, Decimal] = {
            row.format: Decimal(str(row.hourly_rate)) for row in price_rows
        }
        object.__setattr__(self, "_prices_by_format_cache", result)
        return result

    def _invalidate_price_cache(self) -> None:
        """Clear cached prices_by_format after format_prices changes."""
        try:
            object.__delattr__(self, "_prices_by_format_cache")
        except AttributeError:
            pass

    @property
    def sorted_format_prices(self) -> List["ServiceFormatPrice"]:
        """Return pricing rows in a stable format order for serialization."""
        price_rows = list(getattr(self, "format_prices", None) or [])
        rank = {fmt: idx for idx, fmt in enumerate(SERVICE_PRICE_FORMAT_ORDER)}
        return sorted(price_rows, key=lambda row: rank.get(row.format, len(rank)))

    @property
    def serialized_format_prices(self) -> list[SerializedFormatPrice]:
        """Serialize child format prices for API payloads."""
        return [
            {
                "format": row.format,
                "hourly_rate": Decimal(str(row.hourly_rate)),
            }
            for row in self.sorted_format_prices
        ]

    @property
    def min_hourly_rate(self) -> Optional[Decimal]:
        """Return the lowest enabled hourly rate for headline display/filtering."""
        price_map = self.prices_by_format
        if not price_map:
            return None
        return min(price_map.values())

    def _get_hourly_rate(self) -> Optional[Decimal]:
        """Legacy convenience accessor backed by the minimum enabled format rate."""
        return self.min_hourly_rate

    def _hourly_rate_expression(
        cls,
    ) -> Any:  # noqa: N805 — SQLAlchemy hybrid expression (classmethod by convention)
        return (
            select(func.min(ServiceFormatPrice.hourly_rate))
            .where(ServiceFormatPrice.service_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    hourly_rate = hybrid_property(_get_hourly_rate, expr=_hourly_rate_expression)

    def _set_format_enabled(self, format_name: str, enabled: bool) -> None:
        """Internal helper for legacy boolean setters used by tests and seed scripts."""
        price_rows = list(getattr(self, "format_prices", None) or [])
        existing = next((row for row in price_rows if row.format == format_name), None)
        if enabled:
            if existing is not None:
                return
            seed_rate = self.min_hourly_rate or Decimal("100.00")
            price_rows.append(
                ServiceFormatPrice(
                    format=format_name,
                    hourly_rate=self._coerce_decimal_rate(seed_rate),
                )
            )
            self.format_prices = price_rows
            self._invalidate_price_cache()
            return
        if existing is not None:
            self.format_prices = [row for row in price_rows if row.format != format_name]
            self._invalidate_price_cache()

    def _get_offers_travel(self) -> bool:
        """Whether the service offers lessons at the student's location."""
        return SERVICE_FORMAT_STUDENT_LOCATION in self.prices_by_format

    def _set_offers_travel(self, enabled: bool) -> None:
        self._set_format_enabled(SERVICE_FORMAT_STUDENT_LOCATION, bool(enabled))

    def _offers_travel_expression(cls) -> Any:  # noqa: N805 — SQLAlchemy hybrid expression
        return (
            select(ServiceFormatPrice.id)
            .where(
                ServiceFormatPrice.service_id == cls.id,
                ServiceFormatPrice.format == SERVICE_FORMAT_STUDENT_LOCATION,
            )
            .exists()
        )

    offers_travel = hybrid_property(
        _get_offers_travel,
        fset=_set_offers_travel,
        expr=_offers_travel_expression,
    )

    def _get_offers_at_location(self) -> bool:
        """Whether the service offers lessons at the instructor's location."""
        return SERVICE_FORMAT_INSTRUCTOR_LOCATION in self.prices_by_format

    def _set_offers_at_location(self, enabled: bool) -> None:
        self._set_format_enabled(SERVICE_FORMAT_INSTRUCTOR_LOCATION, bool(enabled))

    def _offers_at_location_expression(cls) -> Any:  # noqa: N805 — SQLAlchemy hybrid expression
        return (
            select(ServiceFormatPrice.id)
            .where(
                ServiceFormatPrice.service_id == cls.id,
                ServiceFormatPrice.format == SERVICE_FORMAT_INSTRUCTOR_LOCATION,
            )
            .exists()
        )

    offers_at_location = hybrid_property(
        _get_offers_at_location,
        fset=_set_offers_at_location,
        expr=_offers_at_location_expression,
    )

    def _get_offers_online(self) -> bool:
        """Whether the service offers online lessons."""
        return SERVICE_FORMAT_ONLINE in self.prices_by_format

    def _set_offers_online(self, enabled: bool) -> None:
        self._set_format_enabled(SERVICE_FORMAT_ONLINE, bool(enabled))

    def _offers_online_expression(cls) -> Any:  # noqa: N805 — SQLAlchemy hybrid expression
        return (
            select(ServiceFormatPrice.id)
            .where(
                ServiceFormatPrice.service_id == cls.id,
                ServiceFormatPrice.format == SERVICE_FORMAT_ONLINE,
            )
            .exists()
        )

    offers_online = hybrid_property(
        _get_offers_online,
        fset=_set_offers_online,
        expr=_offers_online_expression,
    )

    def format_for_booking_location_type(self, location_type: Optional[str]) -> str:
        """Resolve booking semantics to the persisted pricing format."""
        normalized_location = BOOKING_TO_SERVICE_FORMAT.get(
            str(location_type or SERVICE_FORMAT_ONLINE).lower(),
            SERVICE_FORMAT_ONLINE,
        )
        price_map = self.prices_by_format
        if str(location_type or "").lower() != "neutral_location":
            if normalized_location not in price_map:
                raise BusinessRuleException(
                    f"No pricing configured for requested booking format '{normalized_location}'",
                    code="PRICING_FORMAT_NOT_FOUND",
                    details={
                        "location_type": location_type,
                        "requested_format": normalized_location,
                    },
                )
            return normalized_location

        # neutral_location (park, library, etc.) — both parties travel to a third place.
        # Prefer instructor_location rate: the instructor isn't hosting, similar cost structure.
        # Fall back to student_location rate if instructor_location not offered.
        # Never fall back to online — neutral implies a physical meeting.
        if SERVICE_FORMAT_INSTRUCTOR_LOCATION in price_map:
            return SERVICE_FORMAT_INSTRUCTOR_LOCATION
        if SERVICE_FORMAT_STUDENT_LOCATION in price_map:
            return SERVICE_FORMAT_STUDENT_LOCATION

        raise BusinessRuleException(
            "No pricing configured for requested booking format 'neutral_location'",
            code="PRICING_FORMAT_NOT_FOUND",
            details={
                "location_type": location_type,
                "requested_format": "neutral_location",
            },
        )

    def hourly_rate_for_location_type(self, location_type: Optional[str]) -> Decimal:
        """Resolve a booking location type to its configured hourly rate."""
        price_map = self.prices_by_format
        pricing_format = self.format_for_booking_location_type(location_type)
        return price_map[pricing_format]

    def session_price(self, duration_minutes: int, format: str) -> Decimal:
        """
        Calculate the price for a session of given duration.

        Args:
            duration_minutes: Duration of the session in minutes
            format: One of the persisted service pricing formats

        Returns:
            Decimal: Price for the session
        """
        price_map = self.prices_by_format
        if format not in price_map:
            raise ValueError(f"No pricing configured for format '{format}'")
        hourly_rate = price_map[format]
        minutes = Decimal(int(duration_minutes))
        return (hourly_rate * minutes / Decimal("60")).quantize(PRICE_QUANTUM)

    def price_for_booking(self, duration_minutes: int, location_type: Optional[str]) -> Decimal:
        """Calculate a booking total using booking location_type semantics."""
        pricing_format = self.format_for_booking_location_type(location_type)
        return self.session_price(duration_minutes, pricing_format)

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
            "min_hourly_rate": self.min_hourly_rate,
            "format_prices": self.serialized_format_prices,
            "description": self.description
            or (self.catalog_entry.description if self.catalog_entry else None),
            "requirements": self.requirements,
            "duration_options": self.duration_options,
            "equipment_required": self.equipment_required,
            "age_groups": self.age_groups,
            "filter_selections": self.filter_selections,
            "offers_travel": self.offers_travel,
            "offers_at_location": self.offers_at_location,
            "offers_online": self.offers_online,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ServiceFormatPrice(Base):
    """Per-format hourly pricing for an instructor service."""

    __tablename__ = "service_format_pricing"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    service_id = Column(
        String(26),
        ForeignKey("instructor_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    format = Column(String(32), nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("service_id", "format", name="uq_service_format_pricing_service_format"),
        CheckConstraint("hourly_rate > 0", name="check_service_format_price_positive"),
        CheckConstraint("hourly_rate <= 1000", name="check_service_format_price_cap"),
        CheckConstraint(
            "format IN ('student_location', 'instructor_location', 'online')",
            name="check_service_format_price_format",
        ),
        Index("idx_service_format_pricing_format_hourly_rate", "format", "hourly_rate"),
        Index(
            "idx_service_format_pricing_service_covering",
            "service_id",
            postgresql_include=["hourly_rate", "format"],
        ),
    )

    service = relationship("InstructorService", back_populates="format_prices")

    def __repr__(self) -> str:
        return f"<ServiceFormatPrice service_id={self.service_id} format={self.format}>"


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
    avg_price_booked_cents = Column(Integer, nullable=False, default=0)
    price_percentile_25_cents = Column(Integer, nullable=False, default=0)
    price_percentile_50_cents = Column(Integer, nullable=False, default=0)
    price_percentile_75_cents = Column(Integer, nullable=False, default=0)
    most_booked_duration = Column(Integer, nullable=True)
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
    def avg_price_booked(self) -> float:
        return float((self.avg_price_booked_cents or 0) / 100.0)

    @avg_price_booked.setter
    def avg_price_booked(self, value: float | None) -> None:
        self.avg_price_booked_cents = int(round(float(value or 0) * 100))

    @property
    def price_percentile_25(self) -> float:
        return float((self.price_percentile_25_cents or 0) / 100.0)

    @price_percentile_25.setter
    def price_percentile_25(self, value: float | None) -> None:
        self.price_percentile_25_cents = int(round(float(value or 0) * 100))

    @property
    def price_percentile_50(self) -> float:
        return float((self.price_percentile_50_cents or 0) / 100.0)

    @price_percentile_50.setter
    def price_percentile_50(self, value: float | None) -> None:
        self.price_percentile_50_cents = int(round(float(value or 0) * 100))

    @property
    def price_percentile_75(self) -> float:
        return float((self.price_percentile_75_cents or 0) / 100.0)

    @price_percentile_75.setter
    def price_percentile_75(self, value: float | None) -> None:
        self.price_percentile_75_cents = int(round(float(value or 0) * 100))

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
