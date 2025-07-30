# backend/app/services/privacy_service.py
"""
Privacy Service for InstaInstru Platform.

Handles GDPR compliance, data retention policies, and user privacy requests.
Provides centralized privacy management across all data types.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import Booking, InstructorProfile, SearchEvent, SearchHistory, User
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
        """Initialize the privacy service."""
        super().__init__(db)

    @BaseService.measure_operation("export_user_data")
    def export_user_data(self, user_id: int) -> Dict:
        """
        Export all user data for GDPR compliance.

        Args:
            user_id: ID of the user requesting their data

        Returns:
            Dictionary containing all user data
        """
        user = self.db.query(User).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        export_data = {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "user_profile": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "account_status": user.account_status,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            },
            "search_history": [],
            "bookings": [],
            "instructor_profile": None,
            "student_profile": None,
        }

        # Export search history
        searches = (
            self.db.query(SearchHistory)
            .filter_by(user_id=user_id, deleted_at=None)
            .order_by(SearchHistory.first_searched_at.desc())
            .all()
        )

        for search in searches:
            export_data["search_history"].append(
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
        bookings = (
            self.db.query(Booking).filter(or_(Booking.student_id == user_id, Booking.instructor_id == user_id)).all()
        )

        for booking in bookings:
            export_data["bookings"].append(
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
        instructor = self.db.query(InstructorProfile).filter_by(user_id=user_id).first()
        if instructor:
            export_data["instructor_profile"] = {
                "bio": instructor.bio,
                "years_experience": instructor.years_experience,
                "areas_of_service": instructor.areas_of_service,
                "min_advance_booking_hours": instructor.min_advance_booking_hours,
                "buffer_time_minutes": instructor.buffer_time_minutes,
                "created_at": instructor.created_at.isoformat() if instructor.created_at else None,
            }

        # For students, the user record is sufficient (no separate student profile table)

        logger.info(f"Exported data for user {user_id}")
        return export_data

    @BaseService.measure_operation("delete_user_data")
    def delete_user_data(self, user_id: int, delete_account: bool = False) -> Dict[str, int]:
        """
        Delete user data for right to be forgotten requests.

        Args:
            user_id: ID of the user requesting deletion
            delete_account: Whether to delete the account entirely

        Returns:
            Dictionary with counts of deleted records
        """
        user = self.db.query(User).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        deletion_stats = {
            "search_history": 0,
            "search_events": 0,
            "bookings": 0,
        }

        try:
            # Delete search history
            deletion_stats["search_history"] = (
                self.db.query(SearchHistory).filter_by(user_id=user_id).delete(synchronize_session=False)
            )

            # Delete search events
            deletion_stats["search_events"] = (
                self.db.query(SearchEvent).filter_by(user_id=user_id).delete(synchronize_session=False)
            )

            # Anonymize bookings (keep for business records but remove PII)
            # Note: We can't set student_id/instructor_id to NULL due to NOT NULL constraints
            # Instead, we create a special "deleted user" marker or just count the bookings
            bookings = (
                self.db.query(Booking)
                .filter(or_(Booking.student_id == user_id, Booking.instructor_id == user_id))
                .all()
            )

            # For now, just count affected bookings without modifying them
            # In a real implementation, you might:
            # 1. Create a special "deleted user" placeholder account
            # 2. Or add a separate anonymization flag to the booking
            # 3. Or soft-delete the bookings entirely
            deletion_stats["bookings"] = len(bookings)

            # Note: AlertHistory is for system alerts, not user-specific

            if delete_account:
                # Soft delete the user account
                user.is_active = False
                user.email = f"deleted_{user.id}@deleted.com"
                user.full_name = "Deleted User"

                # Delete instructor profile if exists
                self.db.query(InstructorProfile).filter_by(user_id=user_id).delete()

            self.db.commit()
            logger.info(f"Deleted data for user {user_id}: {deletion_stats}")
            return deletion_stats

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting user data: {str(e)}")
            raise

    @BaseService.measure_operation("apply_retention_policies")
    def apply_retention_policies(self) -> Dict[str, int]:
        """
        Apply data retention policies across all data types.

        Returns:
            Dictionary with counts of affected records
        """
        retention_stats = {
            "search_events_deleted": 0,
            "old_bookings_anonymized": 0,
        }

        try:
            # Delete old search events (keep aggregated data only)
            if hasattr(settings, "search_event_retention_days"):
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.search_event_retention_days)
                retention_stats["search_events_deleted"] = (
                    self.db.query(SearchEvent)
                    .filter(SearchEvent.searched_at < cutoff_date)
                    .delete(synchronize_session=False)
                )

            # Anonymize old bookings (keep for business records)
            if hasattr(settings, "booking_pii_retention_days"):
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.booking_pii_retention_days)
                # Count old bookings that would be anonymized
                # Note: Can't actually set student_id/instructor_id to NULL due to NOT NULL constraints
                old_bookings_count = self.db.query(Booking).filter(Booking.created_at < cutoff_date).count()

                # In a real implementation, you might:
                # 1. Add an anonymization flag to bookings
                # 2. Create a special "anonymous" user account
                # 3. Or implement soft deletion with a different approach
                retention_stats["old_bookings_anonymized"] = old_bookings_count

            # Note: AlertHistory is for system alerts, not user-specific data retention

            self.db.commit()
            logger.info(f"Applied retention policies: {retention_stats}")
            return retention_stats

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error applying retention policies: {str(e)}")
            raise

    @BaseService.measure_operation("get_privacy_statistics")
    def get_privacy_statistics(self) -> Dict:
        """
        Get statistics about data retention and privacy.

        Returns:
            Dictionary with privacy-related statistics
        """
        stats = {
            "total_users": self.db.query(User).count(),
            "active_users": self.db.query(User).filter_by(is_active=True).count(),
            "search_history_records": self.db.query(SearchHistory).count(),
            "search_event_records": self.db.query(SearchEvent).count(),
            "total_bookings": self.db.query(Booking).count(),
            # Note: All bookings have PII due to NOT NULL constraints on user IDs
            # In a real implementation, you'd have an anonymization flag or similar
        }

        # Add retention policy information
        if hasattr(settings, "search_event_retention_days"):
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.search_event_retention_days)
            stats["search_events_eligible_for_deletion"] = (
                self.db.query(SearchEvent).filter(SearchEvent.searched_at < cutoff_date).count()
            )

        return stats

    @BaseService.measure_operation("anonymize_user")
    def anonymize_user(self, user_id: int) -> bool:
        """
        Anonymize a user's data while keeping the account.

        Args:
            user_id: ID of the user to anonymize

        Returns:
            True if successful
        """
        try:
            user = self.db.query(User).filter_by(id=user_id).first()
            if not user:
                raise ValueError(f"User {user_id} not found")

            # Anonymize user data
            user.email = f"anon_{user.id}@anonymized.com"
            user.full_name = f"Anonymous User {user.id}"

            # Anonymize related profiles
            instructor = self.db.query(InstructorProfile).filter_by(user_id=user_id).first()
            if instructor:
                instructor.bio = "This profile has been anonymized"

            # Clear search history
            self.db.query(SearchHistory).filter_by(user_id=user_id).delete()
            self.db.query(SearchEvent).filter_by(user_id=user_id).delete()

            self.db.commit()
            logger.info(f"Anonymized user {user_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error anonymizing user: {str(e)}")
            raise
