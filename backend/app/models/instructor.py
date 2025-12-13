# backend/app/models/instructor.py
"""
Instructor Profile model for the InstaInstru platform.

This module defines the InstructorProfile model which extends a User
to have instructor-specific attributes and capabilities. Each instructor
has a profile that contains their bio, experience, service areas, and
booking preferences.
"""

import logging
from typing import TYPE_CHECKING, Any, List, Optional, Set, cast

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.sql import func
import ulid

from ..database import Base

if TYPE_CHECKING:
    from .service_catalog import InstructorService

logger = logging.getLogger(__name__)


class InstructorProfile(Base):
    """
    Model representing an instructor's profile.

    An instructor profile contains all the instructor-specific information
    beyond the basic user data. This includes their professional details,
    service offerings, and booking preferences.

    Attributes:
        id: Primary key
        user_id: Foreign key to users table (one-to-one relationship)
        bio: Professional biography/description
        years_experience: Years of teaching experience
        min_advance_booking_hours: Minimum hours advance notice for bookings
        buffer_time_minutes: Buffer time between bookings
        created_at: Timestamp when profile was created
        updated_at: Timestamp when profile was last updated

    Relationships:
        user: The User this profile belongs to
        services: List of services offered by this instructor

    Business Rules:
        - Each user can have at most one instructor profile
        - Deleting a profile soft deletes all services (preserves bookings)
        - Profile deletion reverts user role to STUDENT
    """

    __tablename__ = "instructor_profiles"

    # Primary key
    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))

    # Foreign key to user (one-to-one relationship)
    user_id = Column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Profile information
    bio = Column(Text, nullable=True)
    years_experience = Column(Integer, nullable=True)

    # Booking preferences
    min_advance_booking_hours = Column(Integer, nullable=False, default=24)
    buffer_time_minutes = Column(Integer, nullable=False, default=0)
    current_tier_pct = Column(Numeric(5, 2), nullable=False, default=15.00, server_default="15.00")
    last_tier_eval_at = Column(DateTime(timezone=True), nullable=True)

    # Onboarding status fields
    skills_configured = Column(Boolean, nullable=False, default=False)
    identity_verified_at = Column(DateTime(timezone=True), nullable=True)
    identity_verification_session_id = Column(String(255), nullable=True)
    background_check_object_key = Column(String(512), nullable=True)
    background_check_uploaded_at = Column(DateTime(timezone=True), nullable=True)
    onboarding_completed_at = Column(DateTime(timezone=True), nullable=True)
    is_live = Column(Boolean, nullable=False, default=False)

    # Background check status tracking
    bgc_status = Column(String(20), nullable=True)
    _bgc_report_id = Column("bgc_report_id", Text, nullable=True)
    bgc_completed_at = Column(DateTime(timezone=True), nullable=True)
    bgc_report_result = Column(String(32), nullable=True)
    bgc_env = Column(String(20), nullable=False, default="sandbox", server_default="sandbox")
    bgc_valid_until = Column(DateTime(timezone=True), nullable=True)
    bgc_eta = Column(DateTime(timezone=True), nullable=True)
    bgc_invited_at = Column(DateTime(timezone=True), nullable=True)
    bgc_includes_canceled = Column(Boolean, nullable=False, default=False, server_default="false")
    bgc_in_dispute = Column(Boolean, nullable=False, default=False, server_default="false")
    bgc_dispute_note = Column(Text, nullable=True)
    bgc_dispute_opened_at = Column(DateTime(timezone=True), nullable=True)
    bgc_dispute_resolved_at = Column(DateTime(timezone=True), nullable=True)

    bgc_pre_adverse_notice_id = Column(String(26), nullable=True)
    bgc_pre_adverse_sent_at = Column(DateTime(timezone=True), nullable=True)
    bgc_final_adverse_sent_at = Column(DateTime(timezone=True), nullable=True)
    bgc_review_email_sent_at = Column(DateTime(timezone=True), nullable=True)
    checkr_candidate_id = Column(String(64), nullable=True)
    checkr_invitation_id = Column(String(64), nullable=True)
    bgc_note = Column(Text, nullable=True)

    def _get_bgc_report_id(self) -> str | None:
        """Decrypt the stored background-check report identifier."""

        raw_value = getattr(self, "_bgc_report_id", None)
        if raw_value in (None, ""):
            return raw_value

        raw_value_str = cast(str, raw_value)

        from ..core.crypto import decrypt_report_token
        from ..core.metrics import BGC_REPORT_ID_DECRYPT_TOTAL

        try:
            decrypted = decrypt_report_token(raw_value_str)
        except ValueError:
            return raw_value_str
        if decrypted != raw_value_str:
            BGC_REPORT_ID_DECRYPT_TOTAL.inc()
        return decrypted

    def _set_bgc_report_id(self, report_id: str | None) -> None:
        """Encrypt inbound background-check report identifiers before storing."""

        if report_id in (None, ""):
            self._bgc_report_id = report_id
            return

        from ..core.crypto import encrypt_report_token
        from ..core.metrics import BGC_REPORT_ID_ENCRYPT_TOTAL

        report_id_str = cast(str, report_id)
        encrypted = encrypt_report_token(report_id_str)
        if encrypted != report_id_str:
            BGC_REPORT_ID_ENCRYPT_TOTAL.labels(source="write").inc()
        self._bgc_report_id = encrypted

    bgc_report_id = synonym(
        "_bgc_report_id", descriptor=property(_get_bgc_report_id, _set_bgc_report_id)
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # NL Search ranking signals
    last_active_at = Column(DateTime(timezone=True), nullable=True)  # Last login/activity
    response_rate = Column(Numeric(5, 2), nullable=True)  # 0.00-100.00 percentage
    profile_completeness = Column(Numeric(3, 2), nullable=True)  # 0.00-1.00 fraction

    # Relationships
    user = relationship(
        "User",
        back_populates="instructor_profile",
        uselist=False,
    )

    # IMPORTANT: Do NOT cascade delete services automatically
    # The service layer handles soft/hard delete logic
    instructor_services = relationship(
        "InstructorService",
        back_populates="instructor_profile",
        cascade="save-update, merge",  # Only cascade saves and merges, NOT deletes
        passive_deletes=True,  # Don't load services just to delete them
    )

    # Background check consents
    bgc_consents = relationship(
        "BGCConsent",
        back_populates="instructor_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BGCConsent.consented_at",
    )

    bgc_adverse_events = relationship(
        "BGCAdverseActionEvent",
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BGCAdverseActionEvent.created_at",
    )

    bgc_history = relationship(
        "BackgroundCheck",
        back_populates="instructor_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BackgroundCheck.created_at",
    )

    # Payment relationship
    stripe_connected_account = relationship(
        "StripeConnectedAccount",
        back_populates="instructor_profile",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "bgc_status IN ('pending','passed','review','failed','consider','canceled')",
            name="ck_instructor_profiles_bgc_status",
        ),
        CheckConstraint(
            "bgc_env IN ('sandbox','production')",
            name="ck_instructor_profiles_bgc_env",
        ),
        CheckConstraint(
            "(NOT is_live) OR (bgc_status = 'passed')",
            name="ck_live_requires_bgc_passed",
        ),
        Index("ix_instructor_profiles_checkr_candidate_id", "checkr_candidate_id"),
        Index("ix_instructor_profiles_checkr_invitation_id", "checkr_invitation_id"),
    )

    def __init__(self, **kwargs: Any) -> None:
        """Initialize instructor profile."""
        super().__init__(**kwargs)
        logger.info(f"Creating instructor profile for user {kwargs.get('user_id')}")

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<InstructorProfile {self.user_id} - {self.years_experience} years>"

    @property
    def active_services(self) -> List["InstructorService"]:
        """
        Get only active services for this instructor.

        Returns:
            List of active InstructorService objects
        """
        services = cast("list[InstructorService]", self.instructor_services)
        return [s for s in services if s.is_active]

    @property
    def has_active_services(self) -> bool:
        """
        Check if instructor has any active services.

        Returns:
            bool: True if at least one service is active
        """
        services = cast("list[InstructorService]", self.instructor_services)
        return any(s.is_active for s in services)

    @property
    def total_services(self) -> int:
        """
        Get total number of services (active and inactive).

        Returns:
            int: Total service count
        """
        services = cast("list[InstructorService]", self.instructor_services)
        return len(services)

    @property
    def offered_categories(self) -> Set[str]:
        """
        Get unique categories offered by this instructor.

        Returns:
            Set of category names
        """
        categories = set()
        for service in self.active_services:
            if service.catalog_entry and service.catalog_entry.category:
                categories.add(service.catalog_entry.category.name)
        return categories

    @property
    def offered_category_slugs(self) -> Set[str]:
        """
        Get unique category slugs offered by this instructor.

        Returns:
            Set of category slugs
        """
        slugs = set()
        for service in self.active_services:
            if service.catalog_entry and service.catalog_entry.category:
                slugs.add(service.catalog_entry.category.slug)
        return slugs

    def offers_service(self, service_catalog_id: int) -> bool:
        """
        Check if instructor offers a specific catalog service.

        Args:
            service_catalog_id: The catalog service ID to check

        Returns:
            bool: True if instructor offers this service actively
        """
        services = cast("list[InstructorService]", self.instructor_services)
        return any(s.service_catalog_id == service_catalog_id and s.is_active for s in services)

    def get_service_by_catalog_id(self, service_catalog_id: int) -> Optional["InstructorService"]:
        """
        Get instructor's service by catalog ID.

        Args:
            service_catalog_id: The catalog service ID

        Returns:
            InstructorService or None if not found/inactive
        """
        services = cast("list[InstructorService]", self.instructor_services)
        for service in services:
            if service.service_catalog_id == service_catalog_id and service.is_active:
                return service
        return None

    def can_accept_booking_at(self, hours_until_booking: int) -> bool:
        """
        Check if instructor accepts bookings with given advance notice.

        Args:
            hours_until_booking: Hours between now and booking time

        Returns:
            bool: True if booking meets advance notice requirement
        """
        required_hours = cast(int, self.min_advance_booking_hours)
        return hours_until_booking >= required_hours

    def to_dict(self, include_services: bool = True) -> dict[str, Any]:
        """
        Convert profile to dictionary for API responses.

        Args:
            include_services: Whether to include services list

        Returns:
            dict: Profile data suitable for JSON serialization
        """
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "bio": self.bio,
            "years_experience": self.years_experience,
            "min_advance_booking_hours": self.min_advance_booking_hours,
            "buffer_time_minutes": self.buffer_time_minutes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_services:
            data["services"] = [s.to_dict() for s in self.active_services]
            data["total_services"] = self.total_services
            data["active_services_count"] = len(self.active_services)

        return data


class BGCConsent(Base):
    """Stored consent acknowledgements for instructor background checks."""

    __tablename__ = "bgc_consent"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    instructor_id = Column(
        String(26), ForeignKey("instructor_profiles.id", ondelete="CASCADE"), nullable=False
    )
    consented_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    consent_version = Column(Text, nullable=False)
    ip_address = Column(String(45), nullable=True)

    instructor_profile = relationship(
        "InstructorProfile", back_populates="bgc_consents", passive_deletes=True
    )

    __table_args__ = (Index("ix_bgc_consent_instructor_id", "instructor_id"),)


class BackgroundCheck(Base):
    """Append-only history log for background check completions."""

    __tablename__ = "background_checks"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    instructor_id = Column(
        String(26), ForeignKey("instructor_profiles.id", ondelete="CASCADE"), nullable=False
    )
    report_id_enc = Column(Text, nullable=True)
    result = Column(String(32), nullable=False)
    package = Column(Text, nullable=True)
    env = Column(String(20), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    instructor_profile = relationship(
        "InstructorProfile", back_populates="bgc_history", passive_deletes=True
    )


class BGCAdverseActionEvent(Base):
    """Persisted events for adverse-action notifications."""

    __tablename__ = "bgc_adverse_action_events"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    profile_id = Column(
        String(26), ForeignKey("instructor_profiles.id", ondelete="CASCADE"), nullable=False
    )
    notice_id = Column(String(26), nullable=False)
    event_type = Column(String(40), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile = relationship("InstructorProfile", back_populates="bgc_adverse_events")

    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "notice_id",
            "event_type",
            name="uq_bgc_adverse_action_events_profile_notice_type",
        ),
        Index("ix_bgc_adverse_action_events_profile", "profile_id"),
    )


class BackgroundJob(Base):
    """Persisted background job entry for retryable workflows."""

    __tablename__ = "background_jobs"

    id = Column(String, primary_key=True, index=True)
    type = Column(String, nullable=False)
    payload = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default="queued")
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BGCWebhookLog(Base):
    """Append-only record of recent Checkr webhook deliveries."""

    __tablename__ = "bgc_webhook_log"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    event_type = Column(String(64), nullable=False)
    delivery_id = Column(String(80), nullable=True)
    resource_id = Column(String(64), nullable=True)
    http_status = Column(Integer, nullable=True)
    payload_json = Column(
        JSONB(astext_type=Text()).with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    signature = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_bgc_webhook_log_event_type_created_at", "event_type", "created_at"),
        Index("ix_bgc_webhook_log_delivery_id", "delivery_id"),
        Index("ix_bgc_webhook_log_http_status", "http_status", "created_at"),
    )


class InstructorPreferredPlace(Base):
    """Persistent preferred places an instructor can teach from or meet."""

    __tablename__ = "instructor_preferred_places"

    id = Column(String(26), primary_key=True, index=True, default=lambda: str(ulid.ULID()))
    instructor_id = Column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String(32), nullable=False)
    address = Column(String(512), nullable=False)
    label = Column(String(64), nullable=True)
    position = Column(SmallInteger, nullable=False, default=0)
    place_id = Column(String(255), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('teaching_location','public_space')",
            name="ck_instructor_preferred_places_kind",
        ),
        UniqueConstraint(
            "instructor_id",
            "kind",
            "address",
            name="uq_instructor_preferred_places_instructor_kind_address",
        ),
        Index(
            "ix_instructor_preferred_places_instructor_kind_position",
            "instructor_id",
            "kind",
            "position",
        ),
    )

    instructor = relationship("User", back_populates="preferred_places")

    def __repr__(self) -> str:
        return (
            f"<InstructorPreferredPlace instructor={self.instructor_id} "
            f"kind={self.kind} pos={self.position} address='{self.address[:50]}'>"
        )
