from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, Date, DateTime, Index, LargeBinary, String
from sqlalchemy.dialects.postgresql import BYTEA

from app.database import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AvailabilityDay(Base):
    __tablename__ = "availability_days"

    instructor_id = Column(String(26), primary_key=True)
    day_date = Column(Date, primary_key=True)
    # 6 bytes for 30-min resolution. On PG we store BYTEA; on SQLite use LargeBinary
    bits = Column(BYTEA().with_variant(LargeBinary(), "sqlite"), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_utc,
        onupdate=_now_utc,
        server_default=sa.func.now(),
    )

    __table_args__ = (Index("ix_avail_days_instructor_date", "instructor_id", "day_date"),)
