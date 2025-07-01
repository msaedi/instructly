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

Usage:
    from app.repositories import BaseRepository, RepositoryFactory

    # In a service:
    repository = RepositoryFactory.create_bulk_operation_repository(db)
    slots = repository.get_slots_by_ids([1, 2, 3])

    # Or use specific repository:
    from app.repositories import BulkOperationRepository
    repo = BulkOperationRepository(db)

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

__all__ = [
    "BaseRepository",
    "IRepository",
    "RepositoryFactory",
    "AvailabilityRepository",
    "SlotManagerRepository",
    "ConflictCheckerRepository",
    "BulkOperationRepository",
    "BookingRepository",
]

# Version info
__version__ = "1.0.0"
