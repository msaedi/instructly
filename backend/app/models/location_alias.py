"""Location alias model for resolving user-entered locations to region boundaries."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func
import ulid

from ..database import Base
from .types import StringArrayType

# Default city ID for NYC (until we have a cities table)
NYC_CITY_ID = "01JDEFAULTNYC0000000000"


class LocationAlias(Base):
    """
    Maps location aliases to region_boundaries.

    Supports:
    - Multi-city (via city_id)
    - Ambiguous locations (requires_clarification + candidate_region_ids)
    - Trust model (status + confidence + user_count)
    - Source tracking (manual, fuzzy, embedding, llm, user_learning)
    """

    __tablename__ = "location_aliases"
    __table_args__ = (
        UniqueConstraint("city_id", "alias_normalized", name="uq_location_aliases_city_alias"),
    )

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Multi-city support
    city_id = Column(
        String(26),
        nullable=False,
        default=NYC_CITY_ID,
        server_default=NYC_CITY_ID,
    )

    # The alias text (normalized)
    alias_normalized = Column(String(255), nullable=False)

    # Resolution outcome - single region
    region_boundary_id = Column(
        String(26),
        ForeignKey("region_boundaries.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Resolution outcome - ambiguous
    requires_clarification = Column(Boolean, nullable=False, default=False, server_default="false")
    candidate_region_ids = Column(StringArrayType, nullable=True)

    # Trust model
    status = Column(String(20), nullable=False, default="active", server_default="active")
    # Values: 'pending_review', 'active', 'deprecated'

    # Evidence tracking
    confidence = Column(Float, nullable=False, default=1.0, server_default="1.0")
    source = Column(String(50), nullable=False, default="manual", server_default="manual")
    # Values: 'manual', 'fuzzy', 'embedding', 'llm', 'user_learning'
    user_count = Column(Integer, nullable=False, default=1, server_default="1")

    # Classification
    alias_type = Column(String(20), nullable=True)
    # Values: 'abbreviation', 'colloquial', 'landmark', 'typo'

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deprecated_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LocationAlias {self.alias_normalized} -> {self.region_boundary_id}>"

    @property
    def is_trusted(self) -> bool:
        """Check if this alias should be used in Tier 2 lookups."""
        if self.status == "active":
            return True
        if self.status == "pending_review":
            return bool(self.confidence >= 0.9 and self.user_count >= 5)
        return False

    @property
    def is_resolved(self) -> bool:
        """Check if this alias resolves to a single region."""
        return self.region_boundary_id is not None and not self.requires_clarification

    @property
    def is_ambiguous(self) -> bool:
        """Check if this alias is ambiguous (multiple candidates)."""
        return bool(self.requires_clarification and self.candidate_region_ids)
