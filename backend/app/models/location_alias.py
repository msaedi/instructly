"""Location alias model for resolving user-entered locations to region boundaries."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.sql import func
import ulid

from ..database import Base


class LocationAlias(Base):
    """Maps abbreviations/colloquialisms to a region_boundaries row."""

    __tablename__ = "location_aliases"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    alias = Column(String(100), nullable=False, unique=True)
    region_boundary_id = Column(
        String(26),
        ForeignKey("region_boundaries.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias_type = Column(String(20), nullable=False, server_default="abbreviation")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
