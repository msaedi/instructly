"""Beta program models: invites and access grants."""

from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func
import ulid

from ..database import Base


class BetaInvite(Base):
    __tablename__ = "beta_invites"
    __table_args__ = (
        CheckConstraint(
            "role IN ('instructor_beta', 'student_beta')",
            name="ck_beta_invites_role",
        ),
    )

    # ULID primary key
    id: str = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))

    # Unique human-facing code (8+ uppercase alphanumeric)
    code: str = Column(String(16), unique=True, index=True, nullable=False)

    # Optional pre-associated email for convenience/prefill
    email: Optional[str] = Column(String(255), nullable=True, index=True)

    # Role: 'instructor_beta' | 'student_beta'
    role: str = Column(String(32), nullable=False, default="instructor_beta")
    grant_founding_status = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    used_by_user_id: Optional[str] = Column(
        String(26), ForeignKey("users.id"), nullable=True, index=True
    )

    # Free-form metadata: source, campaign, cohort, etc. (map to DB column named 'metadata')
    metadata_json = Column("metadata", JSON, nullable=True)


class BetaAccess(Base):
    __tablename__ = "beta_access"

    id: str = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))

    user_id: str = Column(String(26), ForeignKey("users.id"), nullable=False, index=True)

    # 'instructor_beta' | 'student_beta' | 'admin'
    role: str = Column(String(32), nullable=False)

    # Foreign key to invites by code (code is unique)
    invited_by_code: Optional[str] = Column(
        String(16), ForeignKey("beta_invites.code"), nullable=True, index=True
    )

    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 'instructor_only' | 'alpha' | 'open_beta'
    phase: str = Column(String(32), nullable=False, default="instructor_only")

    __table_args__ = (
        # Avoid duplicate grants for same user+role in same phase
        UniqueConstraint("user_id", "role", "phase", name="uq_beta_access_user_role_phase"),
    )


class BetaSettings(Base):
    __tablename__ = "beta_settings"

    id: str = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    beta_disabled = Column(Boolean, nullable=False, default=False)
    beta_phase = Column(String(32), nullable=False, default="instructor_only")
    allow_signup_without_invite = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
