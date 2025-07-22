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
    from .booking_repository import BookingRepository
    from .bulk_operation_repository import BulkOperationRepository
    from .conflict_checker_repository import ConflictCheckerRepository
    from .instructor_profile_repository import InstructorProfileRepository
    from .service_catalog_repository import ServiceAnalyticsRepository, ServiceCatalogRepository
    from .slot_manager_repository import SlotManagerRepository
    from .week_operation_repository import WeekOperationRepository


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

    @staticmethod
    def create_booking_repository(db: Session) -> "BookingRepository":
        """Create repository for booking operations."""
        from .booking_repository import BookingRepository

        return BookingRepository(db)

    @staticmethod
    def create_week_operation_repository(db: Session) -> "WeekOperationRepository":
        """Create repository for week operation queries."""
        from .week_operation_repository import WeekOperationRepository

        return WeekOperationRepository(db)

    @staticmethod
    def create_instructor_profile_repository(db: Session) -> "InstructorProfileRepository":
        """Create repository for instructor profile operations with optimized queries."""
        from .instructor_profile_repository import InstructorProfileRepository

        return InstructorProfileRepository(db)

    @staticmethod
    def create_service_catalog_repository(db: Session) -> "ServiceCatalogRepository":
        """Create repository for service catalog operations with vector search."""
        from .service_catalog_repository import ServiceCatalogRepository

        return ServiceCatalogRepository(db)

    @staticmethod
    def create_service_analytics_repository(db: Session) -> "ServiceAnalyticsRepository":
        """Create repository for service analytics operations."""
        from .service_catalog_repository import ServiceAnalyticsRepository

        return ServiceAnalyticsRepository(db)
