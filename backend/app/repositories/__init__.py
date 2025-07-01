# backend/app/repositories/__init__.py
"""
Repository Pattern Implementation for InstaInstru Platform

This package provides the repository layer for data access,
separating business logic from database queries.

Key Components:
- BaseRepository: Foundation for all repositories with generic CRUD operations
- IRepository: Interface defining required methods for all repositories
- RepositoryFactory: Factory for creating repository instances
- AvailabilityRepository: Repository for availability operations (15+ methods)
- SlotManagerRepository: Repository for slot management (13 methods)
- ConflictCheckerRepository: Repository for conflict checking (13 methods)
- BulkOperationRepository: Repository for bulk operations (13 methods)
- BookingRepository: Repository for booking operations
- WeekOperationRepository: Repository for week operations (15 methods)

Usage:
    from app.repositories import BaseRepository, RepositoryFactory

    # In a service:
    repository = RepositoryFactory.create_week_operation_repository(db)
    bookings = repository.get_week_bookings_with_slots(instructor_id, week_dates)

    # Or use specific repository:
    from app.repositories import WeekOperationRepository
    repo = WeekOperationRepository(db)

Benefits:
- Separation of data access from business logic
- Easier testing with repository mocks
- Consistent data access patterns
- Future flexibility to change data sources
"""

# Import specific repositories as they are created
from .availability_repository import AvailabilityRepository
from .base_repository import BaseRepository, IRepository
from .booking_repository import BookingRepository
from .bulk_operation_repository import BulkOperationRepository
from .conflict_checker_repository import ConflictCheckerRepository
from .factory import RepositoryFactory
from .slot_manager_repository import SlotManagerRepository
from .week_operation_repository import WeekOperationRepository

__all__ = [
    "BaseRepository",
    "IRepository",
    "RepositoryFactory",
    "AvailabilityRepository",
    "SlotManagerRepository",
    "ConflictCheckerRepository",
    "BulkOperationRepository",
    "BookingRepository",
    "WeekOperationRepository",
]

# Version info
__version__ = "1.0.0"
