# backend/app/repositories/__init__.py
"""
Repository Pattern Implementation for InstaInstru Platform

This package provides the repository layer for data access,
separating business logic from database queries.

Key Components:
- BaseRepository: Foundation for all repositories
- IRepository: Interface defining required methods
- RepositoryFactory: Factory for creating repository instances
- AvailabilityRepository: Repository for availability operations
- SlotManagerRepository: Repository for slot management
- ConflictCheckerRepository: Repository for conflict checking

Usage:
    from app.repositories import BaseRepository, RepositoryFactory

    # In a service:
    repository = RepositoryFactory.create_conflict_checker_repository(db)
    bookings = repository.get_bookings_for_conflict_check(instructor_id, date)
"""

# Import specific repositories as they are created
from .availability_repository import AvailabilityRepository
from .base_repository import BaseRepository, IRepository
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
]

# Version info
__version__ = "1.0.0"
