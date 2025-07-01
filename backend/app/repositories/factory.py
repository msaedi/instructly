# backend/app/repositories/factory.py
"""
Repository Factory for InstaInstru Platform

Provides centralized creation of repository instances,
ensuring consistent initialization and dependency injection.

This factory will grow as we add more specific repositories.
"""

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from .base_repository import BaseRepository

# Avoid circular imports
if TYPE_CHECKING:
    from .availability_repository import AvailabilityRepository
    from .bulk_operation_repository import BulkOperationRepository
    from .conflict_checker_repository import ConflictCheckerRepository
    from .slot_manager_repository import SlotManagerRepository


class RepositoryFactory:
    """
    Factory class for creating repository instances.

    Centralizes repository creation to ensure consistent initialization
    and makes it easy to swap implementations if needed.
    """

    @staticmethod
    def create_base_repository(db: Session, model) -> BaseRepository:
        """
        Create a generic base repository for any model.

        Args:
            db: Database session
            model: SQLAlchemy model class

        Returns:
            BaseRepository instance
        """
        return BaseRepository(db, model)

    @staticmethod
    def create_slot_manager_repository(db: Session) -> "SlotManagerRepository":
        """Create repository for slot management operations."""
        from .slot_manager_repository import SlotManagerRepository

        return SlotManagerRepository(db)

    @staticmethod
    def create_availability_repository(db: Session) -> "AvailabilityRepository":
        """Create repository for availability operations."""
        from .availability_repository import AvailabilityRepository

        return AvailabilityRepository(db)

    @staticmethod
    def create_conflict_checker_repository(db: Session) -> "ConflictCheckerRepository":
        """Create repository for conflict checking queries."""
        from .conflict_checker_repository import ConflictCheckerRepository

        return ConflictCheckerRepository(db)

    @staticmethod
    def create_bulk_operation_repository(db: Session) -> "BulkOperationRepository":
        """Create repository for bulk operation queries."""
        from .bulk_operation_repository import BulkOperationRepository

        return BulkOperationRepository(db)

    # @staticmethod
    # def create_booking_repository(db: Session) -> 'BookingRepository':
    #     """Create repository for booking operations."""
    #     from .booking_repository import BookingRepository
    #     return BookingRepository(db)

    # @staticmethod
    # def create_week_operation_repository(db: Session) -> 'WeekOperationRepository':
    #     """Create repository for week operation queries."""
    #     from .week_operation_repository import WeekOperationRepository
    #     return WeekOperationRepository(db)
