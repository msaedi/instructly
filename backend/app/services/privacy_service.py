# backend/app/services/privacy_service.py
"""
Privacy Service for InstaInstru Platform.

Handles GDPR compliance, data retention policies, and user privacy requests.
Provides centralized privacy management across all data types.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import settings
from ..repositories.factory import RepositoryFactory
from .base import BaseService

logger = logging.getLogger(__name__)


class PrivacyService(BaseService):
    """
    Service for managing user privacy and data retention.

    Handles:
    - GDPR data export requests
    - Right to be forgotten (data deletion)
    - Data retention policies
    - Privacy audit trails
    """

    def __init__(self, db: Session):
        """Initialize the privacy service with repositories."""
        super().__init__(db)
        self.user_repository = RepositoryFactory.create_user_repository(db)
        self.booking_repository = RepositoryFactory.create_booking_repository(db)
        self.instructor_repository = RepositoryFactory.create_instructor_profile_repository(db)
        self.search_history_repository = RepositoryFactory.create_search_history_repository(db)
        self.search_event_repository = RepositoryFactory.create_search_event_repository(db)
        self.service_area_repository = RepositoryFactory.create_instructor_service_area_repository(
            db
        )

    @BaseService.measure_operation("export_user_data")
    def export_user_data(self, user_id: str) -> dict[str, Any]:
        """
        Export all user data for GDPR compliance.

        Args:
            user_id: ID of the user requesting their data

        Returns:
            Dictionary containing all user data
        """
        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        search_history_data: list[dict[str, Any]] = []
        booking_data: list[dict[str, Any]] = []

        export_data: dict[str, Any] = {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "user_profile": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_active": user.is_active,
                "account_status": user.account_status,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            },
            "search_history": search_history_data,
            "bookings": booking_data,
            "instructor_profile": None,
            "student_profile": None,
        }

        # Export search history
        searches = self.search_history_repository.get_user_searches(user_id, exclude_deleted=True)

        for search in searches:
            search_history_data.append(
                {
                    "search_query": search.search_query,
                    "search_type": search.search_type,
                    "results_count": search.results_count,
                    "search_count": search.search_count,
                    "first_searched_at": search.first_searched_at.isoformat(),
                    "last_searched_at": search.last_searched_at.isoformat(),
                }
            )

        # Export bookings
        student_bookings = self.booking_repository.get_student_bookings(user_id)
        instructor_bookings = self.booking_repository.get_instructor_bookings(user_id)
        bookings = student_bookings + instructor_bookings

        for booking in bookings:
            booking_data.append(
                {
                    "id": booking.id,
                    "booking_date": booking.booking_date.isoformat(),
                    "start_time": str(booking.start_time),
                    "end_time": str(booking.end_time),
                    "service_name": booking.service_name,
                    "total_price": float(booking.total_price),
                    "status": booking.status,
                    "role": "instructor" if booking.instructor_id == user_id else "student",
                    "created_at": booking.created_at.isoformat() if booking.created_at else None,
                }
            )

        # Export instructor profile if exists
        instructor = self.instructor_repository.get_by_user_id(user_id)
        if instructor:
            service_area_records = self.service_area_repository.list_for_instructor(user_id)
            service_area_neighborhoods: list[dict[str, Any]] = []
            boroughs: set[str] = set()

            for area in service_area_records:
                region = getattr(area, "neighborhood", None)
                region_code: str | None = getattr(region, "region_code", None)
                region_name: str | None = getattr(region, "region_name", None)
                borough: str | None = getattr(region, "parent_region", None)
                region_meta = getattr(region, "region_metadata", None)

                if isinstance(region_meta, dict):
                    region_code = (
                        region_code or region_meta.get("nta_code") or region_meta.get("ntacode")
                    )
                    region_name = (
                        region_name or region_meta.get("nta_name") or region_meta.get("name")
                    )
                    meta_borough = region_meta.get("borough")
                    if isinstance(meta_borough, str) and meta_borough:
                        borough = meta_borough

                if borough:
                    boroughs.add(borough)

                service_area_neighborhoods.append(
                    {
                        "neighborhood_id": area.neighborhood_id,
                        "ntacode": region_code,
                        "name": region_name,
                        "borough": borough,
                    }
                )

            sorted_boroughs = sorted(boroughs)
            if sorted_boroughs:
                if len(sorted_boroughs) <= 2:
                    service_area_summary = ", ".join(sorted_boroughs)
                else:
                    service_area_summary = f"{sorted_boroughs[0]} + {len(sorted_boroughs) - 1} more"
            else:
                service_area_summary = ""

            export_data["instructor_profile"] = {
                "bio": instructor.bio,
                "years_experience": instructor.years_experience,
                "min_advance_booking_hours": instructor.min_advance_booking_hours,
                "buffer_time_minutes": instructor.buffer_time_minutes,
                "created_at": instructor.created_at.isoformat() if instructor.created_at else None,
                "service_area_neighborhoods": service_area_neighborhoods,
                "service_area_boroughs": sorted_boroughs,
                "service_area_summary": service_area_summary,
            }

        # For students, the user record is sufficient (no separate student profile table)

        logger.info(f"Exported data for user {user_id}")
        return export_data

    @BaseService.measure_operation("delete_user_data")
    def delete_user_data(self, user_id: str, delete_account: bool = False) -> dict[str, int]:
        """
        Delete user data for right to be forgotten requests.

        Args:
            user_id: ID of the user requesting deletion
            delete_account: Whether to delete the account entirely

        Returns:
            Dictionary with counts of deleted records
        """
        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Business rule: Do NOT allow account deletion if there are active/future bookings
        # This applies to both students and instructors
        future_student_bookings = self.booking_repository.get_student_bookings(
            user_id, upcoming_only=True
        )
        future_instructor_bookings = self.booking_repository.get_instructor_bookings(
            user_id, upcoming_only=True
        )
        total_future_bookings = len(future_student_bookings) + len(future_instructor_bookings)
        if delete_account and total_future_bookings > 0:
            # Raise a value error that routes will convert to 400
            raise ValueError(
                "You have active bookings. Please cancel all upcoming bookings before deleting your account."
            )

        deletion_stats: dict[str, int] = {
            "search_history": 0,
            "search_events": 0,
            "bookings": 0,
        }

        try:
            # Delete search history
            deletion_stats["search_history"] = self.search_history_repository.delete_user_searches(
                user_id
            )

            # Delete search events
            deletion_stats["search_events"] = self.search_event_repository.delete_user_events(
                user_id
            )

            # Anonymize bookings (keep for business records but remove PII)
            # Note: We can't set student_id/instructor_id to NULL due to NOT NULL constraints
            # Instead, we create a special "deleted user" marker or just count the bookings
            student_bookings = self.booking_repository.get_student_bookings(user_id)
            instructor_bookings = self.booking_repository.get_instructor_bookings(user_id)
            bookings = student_bookings + instructor_bookings

            # For now, just count affected bookings without modifying them
            # In a real implementation, you might:
            # 1. Create a special "deleted user" placeholder account
            # 2. Or add a separate anonymization flag to the booking
            # 3. Or soft-delete the bookings entirely
            deletion_stats["bookings"] = len(bookings)

            # Note: AlertHistory is for system alerts, not user-specific

            if delete_account:
                # Soft delete the user account (never hard delete to preserve FKs)
                user.is_active = False
                # Mark lifecycle status so auth blocks login
                try:
                    user.account_status = "deactivated"
                except Exception:
                    pass
                # Anonymize PII
                user.email = f"deleted_{user.id}@deleted.com"
                user.first_name = "Deleted"
                user.last_name = "User"
                # Additional PII anonymization
                try:
                    user.phone = None  # phone is nullable
                except Exception:
                    pass
                try:
                    user.zip_code = "00000"  # zip_code is non-nullable; use neutral placeholder
                except Exception:
                    pass

                # Delete instructor profile if exists
                instructor = self.instructor_repository.get_by_user_id(user_id)
                if instructor:
                    self.instructor_repository.delete(instructor.id)

            # repo-pattern-ignore: Transaction commit belongs in service layer
            self.db.commit()
            logger.info(f"Deleted data for user {user_id}: {deletion_stats}")
            return deletion_stats

        except Exception as e:
            # repo-pattern-ignore: Rollback on error belongs in service layer
            self.db.rollback()
            logger.error(f"Error deleting user data: {str(e)}")
            raise

    @BaseService.measure_operation("apply_retention_policies")
    def apply_retention_policies(self) -> dict[str, int]:
        """
        Apply data retention policies across all data types.

        Returns:
            Dictionary with counts of affected records
        """
        retention_stats: dict[str, int] = {
            "search_events_deleted": 0,
            "old_bookings_anonymized": 0,
        }

        try:
            # Delete old search events (keep aggregated data only)
            if hasattr(settings, "search_event_retention_days"):
                cutoff_date = datetime.now(timezone.utc) - timedelta(
                    days=settings.search_event_retention_days
                )
                retention_stats[
                    "search_events_deleted"
                ] = self.search_event_repository.delete_old_events(cutoff_date)

            # Anonymize old bookings (keep for business records)
            if hasattr(settings, "booking_pii_retention_days"):
                cutoff_date = datetime.now(timezone.utc) - timedelta(
                    days=settings.booking_pii_retention_days
                )
                # Count old bookings that would be anonymized
                # Note: Can't actually set student_id/instructor_id to NULL due to NOT NULL constraints
                old_bookings_count = self.booking_repository.count_old_bookings(cutoff_date)

                # In a real implementation, you might:
                # 1. Add an anonymization flag to bookings
                # 2. Create a special "anonymous" user account
                # 3. Or implement soft deletion with a different approach
                retention_stats["old_bookings_anonymized"] = old_bookings_count

            # Note: AlertHistory is for system alerts, not user-specific data retention

            # repo-pattern-ignore: Transaction commit belongs in service layer
            self.db.commit()
            logger.info(f"Applied retention policies: {retention_stats}")
            return retention_stats

        except Exception as e:
            # repo-pattern-ignore: Rollback on error belongs in service layer
            self.db.rollback()
            logger.error(f"Error applying retention policies: {str(e)}")
            raise

    @BaseService.measure_operation("get_privacy_statistics")
    def get_privacy_statistics(self) -> dict[str, Any]:
        """
        Get statistics about data retention and privacy.

        Returns:
            Dictionary with privacy-related statistics
        """
        stats: dict[str, Any] = {
            "total_users": self.user_repository.count_all(),
            "active_users": self.user_repository.count_active(),
            "search_history_records": self.search_history_repository.count_all_searches(),
            "search_event_records": self.search_event_repository.count_all_events(),
            "total_bookings": self.booking_repository.count(),
            # Note: All bookings have PII due to NOT NULL constraints on user IDs
            # In a real implementation, you'd have an anonymization flag or similar
        }

        # Add retention policy information
        if hasattr(settings, "search_event_retention_days"):
            cutoff_date = datetime.now(timezone.utc) - timedelta(
                days=settings.search_event_retention_days
            )
            stats[
                "search_events_eligible_for_deletion"
            ] = self.search_event_repository.count_old_events(cutoff_date)

        return stats

    @BaseService.measure_operation("anonymize_user")
    def anonymize_user(self, user_id: str) -> bool:
        """
        Anonymize a user's data while keeping the account.

        Args:
            user_id: ID of the user to anonymize

        Returns:
            True if successful
        """
        try:
            user = self.user_repository.get_by_id(user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")

            # Anonymize user data
            user.email = f"anon_{user.id}@anonymized.com"
            user.first_name = "Anonymous"
            user.last_name = f"User{user.id}"

            # Anonymize related profiles
            instructor = self.instructor_repository.get_by_user_id(user_id)
            if instructor:
                instructor.bio = "This profile has been anonymized"

            # Clear search history
            self.search_history_repository.delete_user_searches(user_id)
            self.search_event_repository.delete_user_events(user_id)

            # repo-pattern-ignore: Transaction commit belongs in service layer
            self.db.commit()
            logger.info(f"Anonymized user {user_id}")
            return True

        except Exception as e:
            # repo-pattern-ignore: Rollback on error belongs in service layer
            self.db.rollback()
            logger.error(f"Error anonymizing user: {str(e)}")
            raise
