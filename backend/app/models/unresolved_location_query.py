"""Model for tracking location queries that could not be resolved."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func
import ulid

from ..database import Base
from .location_alias import NYC_CITY_ID
from .types import StringArrayType


class UnresolvedLocationQuery(Base):
    """
    Tracks location queries that couldn't be resolved.

    Used for:
    - Identifying gaps in alias coverage
    - Admin review and manual alias creation
    - Self-learning candidate identification
    """

    __tablename__ = "unresolved_location_queries"
    __table_args__ = (
        UniqueConstraint("city_id", "query_normalized", name="uq_unresolved_queries_city_query"),
    )

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Multi-city support
    city_id = Column(String(26), nullable=False, default=NYC_CITY_ID, server_default=NYC_CITY_ID)

    # The query text (normalized)
    query_normalized = Column(String(255), nullable=False)

    # Sample original queries (for debugging)
    sample_original_queries = Column(StringArrayType, nullable=False, default=list)

    # Counters
    search_count = Column(Integer, nullable=False, default=1, server_default="1")
    unique_user_count = Column(Integer, nullable=False, default=1, server_default="1")

    # Timestamps
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Admin review
    reviewed = Column(Boolean, nullable=False, default=False, server_default="false")
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String(26), nullable=True)
    review_notes = Column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<UnresolvedLocationQuery {self.query_normalized!r} ({self.unique_user_count} users)>"
        )
