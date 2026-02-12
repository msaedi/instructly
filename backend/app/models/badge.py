"""
SQLAlchemy models for student badges.

These models mirror the badge tables introduced in the baseline migration and
provide ORM mappings for repository/service usage.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.sql import func
import ulid

from ..database import Base


class BadgeDefinition(Base):
    """Catalog entry describing a badge students can earn."""

    __tablename__ = "badge_definitions"

    id: Mapped[str] = Column(
        String(26),
        primary_key=True,
        default=lambda: str(ulid.ULID()),
    )
    slug: Mapped[str] = Column(String(100), unique=True, nullable=False)
    name: Mapped[str] = Column(String(200), nullable=False)
    description: Mapped[Optional[str]] = Column(Text, nullable=True)
    criteria_type: Mapped[Optional[str]] = Column(String(50), nullable=True)
    criteria_config: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    icon_key: Mapped[Optional[str]] = Column(String(100), nullable=True)
    display_order: Mapped[Optional[int]] = Column(Integer, nullable=True)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    created_at: Mapped = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    student_badges: Mapped[list["StudentBadge"]] = relationship(
        "StudentBadge",
        back_populates="badge",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    progress_entries: Mapped[list["BadgeProgress"]] = relationship(
        "BadgeProgress",
        back_populates="badge",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class StudentBadge(Base):
    """Badge instance earned (or pending) for a specific student."""

    __tablename__ = "student_badges"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "badge_id",
            name="uq_student_badges_student_badge",
        ),
    )

    id: Mapped[str] = Column(
        String(26),
        primary_key=True,
        default=lambda: str(ulid.ULID()),
    )
    student_id: Mapped[str] = Column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    badge_id: Mapped[str] = Column(
        String(26),
        ForeignKey("badge_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    awarded_at: Mapped = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    progress_snapshot: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    status: Mapped[str] = Column(String(16), nullable=False, default="pending")
    hold_until: Mapped[Optional] = Column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[Optional] = Column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional] = Column(DateTime(timezone=True), nullable=True)

    badge: Mapped["BadgeDefinition"] = relationship(
        "BadgeDefinition", back_populates="student_badges"
    )


class BadgeProgress(Base):
    """Ongoing progress toward earning a badge for a student."""

    __tablename__ = "badge_progress"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "badge_id",
            name="uq_badge_progress_student_badge",
        ),
    )

    id: Mapped[str] = Column(
        String(26),
        primary_key=True,
        default=lambda: str(ulid.ULID()),
    )
    student_id: Mapped[str] = Column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    badge_id: Mapped[str] = Column(
        String(26),
        ForeignKey("badge_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_progress: Mapped[dict] = Column(JSON, nullable=False)
    last_updated: Mapped = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    badge: Mapped["BadgeDefinition"] = relationship(
        "BadgeDefinition", back_populates="progress_entries"
    )


__all__ = ["BadgeDefinition", "StudentBadge", "BadgeProgress"]
