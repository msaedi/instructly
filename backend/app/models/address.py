"""
Address and spatial models for InstaInstru.

This module defines ORM models for:
- UserAddress: Optional multiple addresses per user with soft-delete and default flag
- NYCNeighborhood: Neighborhood polygons for NYC enrichment and instructor service areas
- InstructorServiceArea: Link table between instructor users and neighborhoods
"""

from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import ulid

from ..database import Base

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .region_boundary import RegionBoundary
    from .user import User


class UserAddress(Base):
    """
    Optional user address record.

    Multiple addresses per user are supported. A single default address can be chosen per user.
    Soft delete via is_active flag. Geometry column exists in DB but is not mapped here to avoid geoalchemy2 dependency.
    """

    __tablename__ = "user_addresses"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    user_id = Column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Labels
    label = Column(String(20), nullable=True)  # 'home' | 'work' | 'other'
    custom_label = Column(String(50), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)

    # Recipient
    recipient_name = Column(String(100), nullable=True)

    # Address lines
    street_line1 = Column(String(255), nullable=False)
    street_line2 = Column(String(255), nullable=True)
    locality = Column(String(100), nullable=False)  # City/Town
    administrative_area = Column(String(100), nullable=False)  # State/Province
    postal_code = Column(String(20), nullable=False)
    country_code = Column(String(2), nullable=False, default="US")

    # Coordinates (geometry exists in DB; we map lat/lon for ease of use)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)

    # Generic location hierarchy (global)
    district = Column(String(100), nullable=True)
    neighborhood = Column(String(100), nullable=True)
    subneighborhood = Column(String(100), nullable=True)

    # Flexible metadata for region-specific details
    location_metadata = Column(JSON, nullable=True)

    # Provider references
    place_id = Column(String(255), nullable=True)
    verification_status = Column(String(20), nullable=False, default="unverified")
    normalized_payload = Column(JSON, nullable=True)

    # Removed NYC-specific columns in favor of generic fields + metadata

    # Metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('unverified', 'verified')",
            name="ck_user_addresses_verification_status",
        ),
        CheckConstraint(
            "label IS NULL OR label IN ('home','work','other')",
            name="ck_user_addresses_label",
        ),
        CheckConstraint(
            "label != 'other' OR custom_label IS NOT NULL",
            name="ck_user_addresses_other_label_has_custom",
        ),
    )

    user = relationship("User", backref="addresses")

    def __repr__(self) -> str:
        return f"<UserAddress {self.id} user={self.user_id} default={self.is_default} active={self.is_active}>"


class NYCNeighborhood(Base):
    """NYC neighborhood polygon for enrichment and service areas."""

    __tablename__ = "nyc_neighborhoods"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    ntacode = Column(String(10), unique=True, nullable=True)
    ntaname = Column(String(100), nullable=True)
    borough = Column(String(50), nullable=True)
    community_district = Column(Integer, nullable=True)
    # boundary geometry is present in DB but not mapped here (avoid geoalchemy2 dependency)
    # centroid geometry is present in DB but not mapped here
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<NYCNeighborhood {self.ntacode} {self.ntaname} ({self.borough})>"


class InstructorServiceArea(Base):
    """Link between instructor (user) and neighborhoods they serve."""

    __tablename__ = "instructor_service_areas"

    instructor_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    neighborhood_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("region_boundaries.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    coverage_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    max_distance_miles: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)

    instructor: Mapped["User"] = relationship(
        "User",
        back_populates="service_areas",
        lazy="joined",
    )
    neighborhood: Mapped["RegionBoundary"] = relationship("RegionBoundary", lazy="joined")

    def __repr__(self) -> str:
        return f"<InstructorServiceArea instructor={self.instructor_id} neighborhood={self.neighborhood_id} active={self.is_active}>"


# Re-export RegionBoundary so downstream imports can rely on the address module
from .region_boundary import RegionBoundary  # noqa: E402  (import at end to avoid circular import)

__all__ = [
    "UserAddress",
    "NYCNeighborhood",
    "InstructorServiceArea",
    "RegionBoundary",
]
