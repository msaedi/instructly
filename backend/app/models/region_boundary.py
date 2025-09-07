"""Generic region boundary model for global city support."""

from datetime import datetime, timezone

import ulid
from sqlalchemy import JSON, Column, DateTime, String

from ..database import Base


class RegionBoundary(Base):
    __tablename__ = "region_boundaries"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    region_type = Column(String(50), nullable=False)  # 'nyc', 'sf', 'toronto', etc.
    region_code = Column(String(50), nullable=True)
    region_name = Column(String(100), nullable=True)
    parent_region = Column(String(100), nullable=True)

    # Geometry columns exist in DB via migration; not mapped here to avoid geoalchemy2 dep
    # boundary POLYGON, centroid POINT (SRID 4326)

    region_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RegionBoundary {self.region_type}:{self.region_code} {self.region_name}>"
