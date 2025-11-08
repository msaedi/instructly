# backend/app/repositories/bulk_operation_repository.py
"""
BulkOperation Repository for InstaInstru Platform

REFOCUSED: This repository provides validation support AND bulk operations for availability.

This repository has been cleaned to focus on validation queries and bulk operations
needed when performing bulk availability modifications. It provides ownership
validation, booking checks, and bulk creation operations.

Key responsibilities:
- Validate slot ownership before bulk operations
- Check for existing bookings that would conflict
- Perform bulk slot creation operations
- Retrieve slot data for validation purposes
- Support cache invalidation for bulk operations

Methods removed:
- slot_exists() → Use AvailabilityRepository
- count_slots_for_date() → Use AvailabilityRepository
- get_instructor_profile() → Use ConflictCheckerRepository
- get_week_slots() → Use WeekOperationRepository
- get_booked_slot_ids() → Use SlotManagerRepository
- slot_has_active_booking() → REMOVED (violates clean architecture)

For single slot CRUD operations, use AvailabilityRepository.
"""

from datetime import date
import logging
from typing import Any, Dict, List, cast

from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..core.exceptions import RepositoryException
from ..models.booking import Booking, BookingStatus

logger = logging.getLogger(__name__)


class BulkOperationRepository:
    """
    Repository for bulk operation validation and execution.

    NOTE: Slot-based bulk operations removed. This repository now only provides
    booking validation methods. All availability operations use bitmap storage.
    """

    def __init__(self, db: Session):
        """Initialize repository."""
        self.db = db
        self.logger = logging.getLogger(__name__)

    # Ownership Validation - REMOVED (slot operations deprecated)

    # Booking Validation

    def has_bookings_on_date(self, instructor_id: str, target_date: date) -> bool:
        """
        Check if instructor has any bookings on a specific date.

        UPDATED: Simplified to check bookings directly without slot join.
        This aligns with clean architecture where bookings exist independently.

        Args:
            instructor_id: The instructor ID
            target_date: The date to check

        Returns:
            True if there are confirmed/completed bookings, False otherwise
        """
        try:
            count = cast(
                int,
                self.db.query(Booking)
                .filter(
                    and_(
                        Booking.instructor_id == instructor_id,
                        Booking.booking_date == target_date,
                        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                    )
                )
                .count(),
            )
            return count > 0

        except SQLAlchemyError as e:
            self.logger.error(f"Error checking bookings: {str(e)}")
            raise RepositoryException(f"Failed to check bookings: {str(e)}")

    # Data Retrieval for Validation - REMOVED (slot operations deprecated)

    # Cache Support - REMOVED (slot operations deprecated)

    # Bulk Operations - REMOVED (slot operations deprecated)

    def bulk_create_slots(self, slots: List[Dict[str, Any]]) -> List[dict[str, Any]]:
        """
        DEPRECATED: Slot-based bulk operations removed. Use bitmap storage instead.
        """
        raise NotImplementedError(
            "Slot-based bulk operations removed. All availability operations must use bitmap storage via AvailabilityDayRepository."
        )
