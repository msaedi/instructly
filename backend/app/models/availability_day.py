from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import ClauseElement

from app.core.constants import BYTES_PER_DAY, TAG_BYTES_PER_DAY
from app.database import Base
from app.utils.bitset import new_empty_tags


class _ZeroedFormatTagsDefault(ClauseElement):  # type: ignore[misc]
    inherit_cache = True


@compiles(_ZeroedFormatTagsDefault, "sqlite")  # type: ignore
def _compile_zeroed_format_tags_sqlite(
    element: _ZeroedFormatTagsDefault, compiler: Any, **kw: object
) -> str:
    return f"zeroblob({TAG_BYTES_PER_DAY})"


@compiles(_ZeroedFormatTagsDefault, "postgresql")  # type: ignore
def _compile_zeroed_format_tags_postgresql(
    element: _ZeroedFormatTagsDefault, compiler: Any, **kw: object
) -> str:
    return f"decode(repeat('00', {TAG_BYTES_PER_DAY}), 'hex')"


class AvailabilityDay(Base):
    __tablename__ = "availability_days"

    instructor_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    day_date = Column(Date, primary_key=True)
    # 36 bytes for 5-min resolution (288 slots/day). On PG we store BYTEA; on SQLite use LargeBinary
    bits = Column(BYTEA().with_variant(LargeBinary(length=BYTES_PER_DAY), "sqlite"), nullable=False)
    format_tags = Column(
        BYTEA().with_variant(LargeBinary(length=TAG_BYTES_PER_DAY), "sqlite"),
        nullable=False,
        default=new_empty_tags,
        server_default=_ZeroedFormatTagsDefault(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        onupdate=sa.func.now(),
        server_default=sa.func.now(),
    )

    __table_args__ = (
        CheckConstraint(f"length(bits) = {BYTES_PER_DAY}", name="ck_bits_length"),
        CheckConstraint(
            f"length(format_tags) = {TAG_BYTES_PER_DAY}",
            name="ck_format_tags_length",
        ),
    )
