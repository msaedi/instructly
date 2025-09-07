"""
Address and spatial models for InstaInstru.

This module defines ORM models for:
- UserAddress: Optional multiple addresses per user with soft-delete and default flag
- NYCNeighborhood: Neighborhood polygons for NYC enrichment and instructor service areas
- InstructorServiceArea: Link table between instructor users and neighborhoods
"""

import logging
from datetime import datetime, timezone

import ulid
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from ..database import Base

logger = logging.getLogger(__name__)


class UserAddress(Base):
    """
    Optional user address record.

    Multiple addresses per user are supported. A single default address can be chosen per user.
    Soft delete via is_active flag. Geometry column exists in DB but is not mapped here to avoid geoalchemy2 dependency.
    """

    __tablename__ = "user_addresses"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    user_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

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

    user = relationship("User", backref="addresses")

    def __repr__(self):
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

    def __repr__(self):
        return f"<NYCNeighborhood {self.ntacode} {self.ntaname} ({self.borough})>"


class InstructorServiceArea(Base):
    """Link between instructor (user) and neighborhoods they serve."""

    __tablename__ = "instructor_service_areas"

    instructor_id = Column(String(26), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    neighborhood_id = Column(String(26), ForeignKey("region_boundaries.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, nullable=False, default=True)
    coverage_type = Column(String(20), nullable=True)
    max_distance_miles = Column(Numeric(5, 2), nullable=True)

    instructor = relationship("User", backref="service_areas")
    # Import locally to avoid circular import at module import time
    neighborhood = relationship("RegionBoundary")

    def __repr__(self):
        return f"<InstructorServiceArea instructor={self.instructor_id} neighborhood={self.neighborhood_id} active={self.is_active}>"
