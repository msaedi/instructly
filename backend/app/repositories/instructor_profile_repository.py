# backend/app/repositories/instructor_profile_repository.py
"""
Instructor Profile Repository for InstaInstru Platform

Handles all data access operations for instructor profiles with
optimized queries for relationships (user and services).

This repository eliminates N+1 query problems by using eager loading
for commonly accessed relationships.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, List, Optional, Sequence, cast

from sqlalchemy import desc, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query, Session, joinedload, selectinload

from ..core.bgc_policy import must_be_verified_for_public
from ..core.crypto import encrypt_str
from ..core.exceptions import RepositoryException
from ..models.address import InstructorServiceArea, RegionBoundary
from ..models.instructor import (
    BackgroundCheck,
    BGCAdverseActionEvent,
    BGCConsent,
    InstructorProfile,
)
from ..models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class InstructorProfileRepository(BaseRepository[InstructorProfile]):
    """
    Repository for instructor profile data access.

    Provides optimized queries with eager loading for user and services
    relationships to prevent N+1 query problems.
    """

    def __init__(self, db: Session):
        """Initialize with InstructorProfile model."""
        super().__init__(db, InstructorProfile)
        self.logger = logging.getLogger(__name__)

    def _apply_verified_filter(self, query: Query) -> Query:
        """Restrict results to verified instructors when required."""

        if must_be_verified_for_public():
            query = query.filter(InstructorProfile.bgc_status == "passed")
        return query

    def get_by_user_id(self, user_id: str) -> Optional[InstructorProfile]:
        """
        Get instructor profile by user ID.

        Used by PrivacyService for data export and deletion.

        Args:
            user_id: The user ID to look up

        Returns:
            InstructorProfile if found, None otherwise
        """
        return cast(
            Optional[InstructorProfile],
            self.db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first(),
        )

    def get_all_with_details(
        self, skip: int = 0, limit: int = 100, include_inactive_services: bool = False
    ) -> List[InstructorProfile]:
        """
        Get all instructor profiles with user and services eager loaded.

        This method solves the N+1 query problem by loading all related
        data in a single query with joins.

        Note: This method returns ALL services regardless of the include_inactive_services
        parameter. The service layer should handle filtering when converting to DTOs.

        UPDATED: Now filters to only include instructors with active account status.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_inactive_services: DEPRECATED - kept for compatibility but ignored

        Returns:
            List of InstructorProfile objects with all relationships loaded
        """
        try:
            query = self.db.query(InstructorProfile)
            query = query.join(InstructorProfile.user)
            query = query.join(User.service_areas, isouter=True)
            query = query.join(InstructorServiceArea.neighborhood, isouter=True)
            query = query.filter(User.account_status == "active")
            query = self._apply_verified_filter(query)
            query = query.options(
                selectinload(InstructorProfile.user)
                .selectinload(User.service_areas)
                .selectinload(InstructorServiceArea.neighborhood),
                selectinload(InstructorProfile.instructor_services).selectinload(
                    Service.catalog_entry
                ),
            )
            query = query.order_by(InstructorProfile.id)
            query = query.distinct().offset(skip).limit(limit)

            profiles = cast(List[InstructorProfile], query.all())

            # Return profiles with all services loaded
            # Let the service layer handle filtering
            return profiles

        except Exception as e:
            self.logger.error(f"Error getting all profiles with details: {str(e)}")
            raise RepositoryException(f"Failed to get instructor profiles: {str(e)}")

    def get_by_user_id_with_details(
        self, user_id: str, include_inactive_services: bool = False
    ) -> Optional[InstructorProfile]:
        """
        Get a single instructor profile by user_id with all relationships loaded.

        Note: This method returns ALL services regardless of the include_inactive_services
        parameter. The service layer should handle filtering when converting to DTOs.

        Args:
            user_id: The user ID
            include_inactive_services: DEPRECATED - kept for compatibility but ignored

        Returns:
            InstructorProfile with all relationships loaded, or None if not found
        """
        try:
            profile = cast(
                Optional[InstructorProfile],
                (
                    self.db.query(InstructorProfile)
                    .join(InstructorProfile.user)
                    .join(User.service_areas, isouter=True)
                    .join(InstructorServiceArea.neighborhood, isouter=True)
                    .options(
                        selectinload(InstructorProfile.user)
                        .selectinload(User.service_areas)
                        .selectinload(InstructorServiceArea.neighborhood),
                        selectinload(InstructorProfile.instructor_services).selectinload(
                            Service.catalog_entry
                        ),
                    )
                    .filter(InstructorProfile.user_id == user_id)
                    .first()
                ),
            )

            # Return profile with all services loaded
            # Let the service layer handle filtering
            return profile

        except Exception as e:
            self.logger.error(f"Error getting profile by user_id: {str(e)}")
            raise RepositoryException(f"Failed to get instructor profile: {str(e)}")

    def get_profiles_by_area(
        self, area: str, skip: int = 0, limit: int = 100
    ) -> List[InstructorProfile]:
        """
        Get instructor profiles that service a specific area.

        UPDATED: Now filters to only include instructors with active account status.

        Args:
            area: The area to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of profiles that service the area
        """
        try:
            base_query = (
                self.db.query(InstructorProfile)
                .join(InstructorProfile.user)
                .filter(User.account_status == "active")
            )
            base_query = self._apply_verified_filter(base_query)

            filtered_query = self._apply_area_filters(base_query, area)

            return cast(
                List[InstructorProfile],
                filtered_query.options(
                    selectinload(InstructorProfile.user),
                    selectinload(InstructorProfile.user)
                    .selectinload(User.service_areas)
                    .selectinload(InstructorServiceArea.neighborhood),
                    selectinload(InstructorProfile.instructor_services).selectinload(
                        Service.catalog_entry
                    ),
                )
                .distinct()
                .offset(skip)
                .limit(limit)
                .all(),
            )
        except Exception as e:
            self.logger.error(f"Error getting profiles by area: {str(e)}")
            raise RepositoryException(f"Failed to get profiles by area: {str(e)}")

    def get_profiles_by_experience(
        self, min_years: int, skip: int = 0, limit: int = 100
    ) -> List[InstructorProfile]:
        """
        Get instructor profiles with minimum years of experience.

        Args:
            min_years: Minimum years of experience
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of profiles with sufficient experience
        """
        try:
            return cast(
                List[InstructorProfile],
                (
                    self.db.query(InstructorProfile)
                    .join(InstructorProfile.user)
                    .join(User.service_areas, isouter=True)
                    .join(InstructorServiceArea.neighborhood, isouter=True)
                    .filter(User.account_status == "active")
                    .options(
                        selectinload(InstructorProfile.user),
                        selectinload(InstructorProfile.user)
                        .selectinload(User.service_areas)
                        .selectinload(InstructorServiceArea.neighborhood),
                        selectinload(InstructorProfile.instructor_services).selectinload(
                            Service.catalog_entry
                        ),
                    )
                    .filter(InstructorProfile.years_experience >= min_years)
                    .distinct()
                    .offset(skip)
                    .limit(limit)
                    .all()
                ),
            )
        except Exception as e:
            self.logger.error(f"Error getting profiles by experience: {str(e)}")
            raise RepositoryException(f"Failed to get profiles by experience: {str(e)}")

    def count_profiles(self) -> int:
        """
        Count total number of instructor profiles.

        Returns:
            Number of profiles
        """
        try:
            return cast(int, self.db.query(InstructorProfile).count())
        except Exception as e:
            self.logger.error(f"Error counting active profiles: {str(e)}")
            raise RepositoryException(f"Failed to count profiles: {str(e)}")

    def count_by_bgc_status(self, status: str) -> int:
        """Return total profiles matching a given background-check status."""

        try:
            total = (
                self.db.query(func.count(InstructorProfile.id))
                .filter(InstructorProfile.bgc_status == status)
                .scalar()
            )
            return int(total or 0)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to count instructor profiles by bgc_status=%s: %s",
                status,
                str(exc),
            )
            raise RepositoryException(
                "Failed to count profiles by background check status"
            ) from exc

    def get_by_id_join_user(self, instructor_id: str) -> Optional[InstructorProfile]:
        """Fetch an instructor profile with user eager-loaded."""

        try:
            return cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .options(joinedload(self.model.user))
                .filter(self.model.id == instructor_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load instructor profile %s with user: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to load instructor profile") from exc

    def latest_consent(self, instructor_id: str) -> Optional[BGCConsent]:
        """Return the most recent consent record for an instructor."""

        return cast(
            Optional[BGCConsent],
            self.db.query(BGCConsent)
            .filter(BGCConsent.instructor_id == instructor_id)
            .order_by(BGCConsent.consented_at.desc())
            .first(),
        )

    def update_bgc(
        self,
        instructor_id: str,
        *,
        status: str,
        report_id: str | None,
        env: str,
    ) -> None:
        """Persist background check metadata for a specific instructor profile."""

        try:
            profile = self.get_by_id(instructor_id, load_relationships=False)
            if not profile:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")

            profile.bgc_status = status
            profile.bgc_report_id = report_id
            profile.bgc_env = env

            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update background check metadata for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException(
                f"Failed to update background check metadata for instructor {instructor_id}"
            ) from exc

    def update_bgc_by_report_id(
        self,
        report_id: str,
        *,
        status: str,
        completed_at: datetime | None = None,
    ) -> int:
        """Update background check fields based on a Checkr report identifier."""

        try:
            profile = self.find_one_by(bgc_report_id=report_id)
            if not profile:
                return 0

            profile.bgc_status = status
            if completed_at is not None:
                profile.bgc_completed_at = completed_at

            self.db.flush()
            return 1
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update background check metadata for report %s: %s",
                report_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException(
                f"Failed to update background check metadata for report {report_id}"
            ) from exc

    def get_by_report_id(self, report_id: str) -> Optional[InstructorProfile]:
        """Return the instructor profile associated with a Checkr report."""

        try:
            return cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .options(joinedload(self.model.user))
                .filter(self.model.bgc_report_id == report_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load instructor profile by report %s: %s",
                report_id,
                str(exc),
            )
            raise RepositoryException("Failed to load instructor profile by report id") from exc

    def update_valid_until(self, instructor_id: str, valid_until: datetime | None) -> None:
        """Persist the background check validity window for an instructor."""

        try:
            profile = self.get_by_id(instructor_id, load_relationships=False)
            if not profile:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")

            profile.bgc_valid_until = valid_until
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update bgc_valid_until for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to update background check validity") from exc

    def set_bgc_invited_at(self, instructor_id: str, when: datetime) -> None:
        """Record when the most recent Checkr invite was sent."""

        try:
            profile = self.get_by_id(instructor_id, load_relationships=False)
            if not profile:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")

            profile.bgc_invited_at = when
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update bgc_invited_at for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to update background check invite timestamp") from exc

    def set_pre_adverse_notice(self, instructor_id: str, notice_id: str, sent_at: datetime) -> None:
        """Persist metadata for the latest pre-adverse notice."""

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update(
                    {
                        self.model.bgc_pre_adverse_notice_id: notice_id,
                        self.model.bgc_pre_adverse_sent_at: sent_at,
                    }
                )
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to persist pre-adverse metadata for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to persist pre-adverse metadata") from exc

    def set_final_adverse_sent_at(self, instructor_id: str, sent_at: datetime) -> None:
        """Store when the final adverse email was delivered."""

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update({self.model.bgc_final_adverse_sent_at: sent_at})
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update final adverse timestamp for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to persist final adverse timestamp") from exc

    def record_adverse_event(self, instructor_id: str, notice_id: str, event_type: str) -> str:
        """Insert an idempotency marker for adverse-action notifications."""

        try:
            event = BGCAdverseActionEvent(
                profile_id=instructor_id, notice_id=notice_id, event_type=event_type
            )
            self.db.add(event)
            self.db.flush()
            return cast(str, event.id)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to record adverse-action event for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to record adverse-action event") from exc

    def has_adverse_event(self, instructor_id: str, notice_id: str, event_type: str) -> bool:
        """Return True if an adverse-action event marker already exists."""

        try:
            exists = (
                self.db.query(BGCAdverseActionEvent.id)
                .filter(
                    BGCAdverseActionEvent.profile_id == instructor_id,
                    BGCAdverseActionEvent.notice_id == notice_id,
                    BGCAdverseActionEvent.event_type == event_type,
                )
                .first()
            )
            return exists is not None
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to check adverse-action event for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to check adverse-action event") from exc

    def count_pending_older_than(self, days: int) -> int:
        """Return count of instructors pending longer than the provided number of days."""

        cutoff = datetime.now(timezone.utc) - timedelta(days=max(days, 0))
        try:
            total = (
                self.db.query(func.count(self.model.id))
                .filter(
                    self.model.bgc_status == "pending",
                    self.model.updated_at <= cutoff,
                )
                .scalar()
            )
            return int(total or 0)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to count pending background checks older than %s days: %s",
                days,
                str(exc),
            )
            raise RepositoryException("Failed to count pending background checks") from exc

    def set_dispute_open(self, instructor_id: str, note: str | None) -> None:
        """Mark an instructor's background check as disputed with optional note."""

        now = datetime.now(timezone.utc)
        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update(
                    {
                        self.model.bgc_in_dispute: True,
                        self.model.bgc_dispute_opened_at: now,
                        self.model.bgc_dispute_resolved_at: None,
                        self.model.bgc_dispute_note: note,
                    }
                )
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to open dispute for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to mark dispute open") from exc

    def set_dispute_resolved(self, instructor_id: str, note: str | None) -> None:
        """Resolve an instructor's background check dispute and persist a note."""

        now = datetime.now(timezone.utc)
        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update(
                    {
                        self.model.bgc_in_dispute: False,
                        self.model.bgc_dispute_resolved_at: now,
                        self.model.bgc_dispute_note: note,
                    }
                )
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to resolve dispute for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to resolve dispute") from exc

    def list_expiring_within(self, days: int, limit: int = 1000) -> list[InstructorProfile]:
        """Return instructors whose background checks expire within the given window."""

        try:
            now = datetime.now(timezone.utc)
            end = now + timedelta(days=max(days, 0))
            results = (
                self.db.query(self.model)
                .options(selectinload(self.model.user))
                .filter(
                    self.model.bgc_valid_until.isnot(None),
                    self.model.bgc_valid_until >= now,
                    self.model.bgc_valid_until <= end,
                )
                .order_by(self.model.bgc_valid_until.asc())
                .limit(limit)
                .all()
            )
            return cast(List[InstructorProfile], results)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to list expiring background checks within %s days: %s",
                days,
                str(exc),
            )
            raise RepositoryException("Failed to list expiring background checks") from exc

    def list_expired(self, limit: int = 1000) -> list[InstructorProfile]:
        """Return instructors whose background checks have expired while live."""

        try:
            now = datetime.now(timezone.utc)
            results = (
                self.db.query(self.model)
                .options(selectinload(self.model.user))
                .filter(
                    self.model.bgc_valid_until.isnot(None),
                    self.model.bgc_valid_until < now,
                    self.model.is_live.is_(True),
                )
                .order_by(self.model.bgc_valid_until.asc())
                .limit(limit)
                .all()
            )
            return cast(List[InstructorProfile], results)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to list expired background checks: %s",
                str(exc),
            )
            raise RepositoryException("Failed to list expired background checks") from exc

    def set_live(self, instructor_id: str, is_live: bool) -> None:
        """Toggle instructor live status without loading the full profile."""

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update({self.model.is_live: is_live})
            )
            if not updated:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update live status for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to update live status") from exc

    def append_history(
        self,
        instructor_id: str,
        report_id: str | None,
        *,
        result: str,
        package: str | None,
        env: str,
        completed_at: datetime,
    ) -> str:
        """Append a background check completion record."""

        try:
            record = BackgroundCheck(
                instructor_id=instructor_id,
                report_id_enc=encrypt_str(report_id) if report_id else None,
                result=result,
                package=package,
                env=env,
                completed_at=completed_at,
            )
            self.db.add(record)
            self.db.flush()
            return str(record.id)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to append background check history for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to append background check history") from exc

    def get_history(
        self,
        instructor_id: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[BackgroundCheck]:
        """Fetch background check history entries in reverse-chronological order."""

        try:
            query = (
                self.db.query(BackgroundCheck)
                .filter(BackgroundCheck.instructor_id == instructor_id)
                .order_by(desc(BackgroundCheck.created_at), desc(BackgroundCheck.id))
            )

            if cursor:
                query = query.filter(BackgroundCheck.id < cursor)

            return list(query.limit(max(limit, 1)).all())
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load background check history for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to load background check history") from exc

    def record_bgc_consent(
        self,
        instructor_id: str,
        *,
        consent_version: str,
        ip_address: str | None,
    ) -> BGCConsent:
        """Persist a new consent acknowledgement for the instructor."""

        try:
            consent = BGCConsent(
                instructor_id=instructor_id,
                consent_version=consent_version,
                consented_at=datetime.now(timezone.utc),
                ip_address=ip_address,
            )
            self.db.add(consent)
            self.db.flush()  # Ensure ULID assigned for downstream use
            return consent
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to persist background check consent for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to record background check consent") from exc

    def has_recent_consent(self, instructor_id: str, window: timedelta) -> bool:
        """Return True when instructor has consented within the provided window."""

        try:
            latest = self.latest_consent(instructor_id)
            if not latest:
                return False
            threshold = datetime.now(timezone.utc) - window
            return bool(latest.consented_at and latest.consented_at >= threshold)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to check background check consent recency for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to verify consent recency") from exc

    def _apply_area_filters(self, query: Any, area: str) -> Any:
        """Apply borough/neighborhood filters to the provided query."""

        normalized = (area or "").strip()
        if not normalized:
            return query

        normalized_lower = normalized.lower()

        return (
            query.join(User.service_areas)
            .join(InstructorServiceArea.neighborhood)
            .filter(
                or_(
                    func.lower(RegionBoundary.parent_region) == normalized_lower,
                    func.lower(RegionBoundary.region_name) == normalized_lower,
                    func.lower(RegionBoundary.region_code) == normalized_lower,
                )
            )
        )

    def find_by_filters(
        self,
        search: Optional[str] = None,
        service_catalog_id: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        age_group: Optional[str] = None,
        boroughs: Optional[Sequence[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[InstructorProfile]:
        """
        Find instructor profiles based on multiple filter criteria.

        All filters are applied with AND logic - profiles must match ALL provided filters.

        Args:
            search: Text search across user name, bio, and service skills (case-insensitive)
            service_catalog_id: Filter by specific service catalog ID
            min_price: Minimum hourly rate filter
            max_price: Maximum hourly rate filter
            boroughs: Optional collection of borough names to filter by (case-insensitive)
            skip: Number of records to skip for pagination
            limit: Maximum number of records to return

        Returns:
            List of InstructorProfile objects matching all provided filters
        """
        import time

        start_time = time.time()

        try:
            # Start with base query including eager loading
            query = (
                self.db.query(InstructorProfile)
                .join(InstructorProfile.user)
                .join(User.service_areas, isouter=True)
                .join(InstructorServiceArea.neighborhood, isouter=True)
                .join(Service, InstructorProfile.id == Service.instructor_profile_id)
                .join(ServiceCatalog, Service.service_catalog_id == ServiceCatalog.id)
                .join(ServiceCategory, ServiceCatalog.category_id == ServiceCategory.id)
                .options(
                    selectinload(InstructorProfile.user),
                    selectinload(InstructorProfile.user)
                    .selectinload(User.service_areas)
                    .selectinload(InstructorServiceArea.neighborhood),
                    selectinload(InstructorProfile.instructor_services).selectinload(
                        Service.catalog_entry
                    ),
                )
            )

            if boroughs:
                normalized_boroughs = [
                    b.lower() for b in boroughs if isinstance(b, str) and b.strip()
                ]
                if normalized_boroughs:
                    query = query.filter(
                        func.lower(RegionBoundary.parent_region).in_(normalized_boroughs)
                    )

            # Apply search filter if provided
            if search:
                search_term = f"%{search}%"
                search.lower()

                # Build search conditions
                search_conditions = [
                    func.concat(User.first_name, " ", User.last_name).ilike(search_term),
                    InstructorProfile.bio.ilike(search_term),
                    ServiceCatalog.name.ilike(search_term),
                    ServiceCatalog.description.ilike(search_term),
                    ServiceCategory.name.ilike(search_term),
                ]

                # Only use array_to_string for PostgreSQL
                # Check if we're using PostgreSQL by looking at the dialect
                if hasattr(self.db.bind, "dialect") and self.db.bind.dialect.name == "postgresql":
                    search_conditions.append(
                        func.array_to_string(ServiceCatalog.search_terms, " ").ilike(search_term)
                    )

                query = query.filter(or_(*search_conditions))

            # Apply service catalog filter if provided
            if service_catalog_id:
                query = query.filter(Service.service_catalog_id == service_catalog_id)

            # Apply price range filters if provided
            if min_price is not None:
                query = query.filter(Service.hourly_rate >= min_price)

            if max_price is not None:
                query = query.filter(Service.hourly_rate <= max_price)

            # Apply age group filter if provided
            if age_group:
                # Use PostgreSQL array_position for reliable membership check on arrays
                if hasattr(self.db.bind, "dialect") and self.db.bind.dialect.name == "postgresql":
                    query = query.filter(
                        func.array_position(Service.age_groups, age_group).isnot(None)
                    )
                else:
                    like_pattern = f'%"{age_group}"%'
                    query = query.filter(Service.age_groups.like(like_pattern))

            # Ensure we only get active services and active instructors
            query = query.filter(Service.is_active == True)
            query = query.filter(User.account_status == "active")
            query = self._apply_verified_filter(query)

            # Remove duplicates (since joins can create multiple rows per profile)
            # and apply pagination
            profiles = cast(
                List[InstructorProfile],
                query.distinct().offset(skip).limit(limit).all(),
            )

            # Log query performance
            query_time = time.time() - start_time
            self.logger.info(
                f"Filter query completed in {query_time:.3f}s - "
                f"Filters: search={bool(search)}, service_catalog_id={bool(service_catalog_id)}, "
                f"price_range={bool(min_price or max_price)}, "
                f"Results: {len(profiles)} profiles"
            )

            # Log slow queries for optimization
            if query_time > 0.5:  # 500ms threshold
                self.logger.warning(
                    f"Slow filter query detected ({query_time:.3f}s) - "
                    f"Consider adding indexes for: "
                    f"{'search' if search else ''} "
                    f"{'service_catalog_id' if service_catalog_id else ''} "
                    f"{'price' if min_price or max_price else ''}"
                )

            return profiles

        except Exception as e:
            self.logger.error(f"Error finding profiles by filters: {str(e)}")
            raise RepositoryException(f"Failed to find profiles by filters: {str(e)}")

    # Override the base eager loading method
    def _apply_eager_loading(self, query: Any) -> Any:
        """
        Apply eager loading for commonly accessed relationships.

        This is called by BaseRepository methods like get_by_id()
        when load_relationships=True.
        """
        return query.options(
            selectinload(InstructorProfile.user)
            .selectinload(User.service_areas)
            .selectinload(InstructorServiceArea.neighborhood),
            selectinload(InstructorProfile.instructor_services).selectinload(Service.catalog_entry),
        )
