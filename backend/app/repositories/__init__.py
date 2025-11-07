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
- InstructorProfileRepository: Repository for instructor profiles with eager loading

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
from .availability_day_repository import AvailabilityDayRepository
from .availability_repository import AvailabilityRepository
from .base_repository import BaseRepository, IRepository
from .booking_repository import BookingRepository
from .bulk_operation_repository import BulkOperationRepository
from .conflict_checker_repository import ConflictCheckerRepository
from .factory import RepositoryFactory
from .instructor_profile_repository import InstructorProfileRepository
from .referral_repository import (
    ReferralAttributionRepository,
    ReferralClickRepository,
    ReferralCodeRepository,
    ReferralLimitRepository,
    ReferralRewardRepository,
    WalletTransactionRepository,
)
from .search_event_repository import SearchEventRepository

# SlotManagerRepository removed - bitmap-only storage now
from .week_operation_repository import WeekOperationRepository

__all__ = [
    "BaseRepository",
    "IRepository",
    "RepositoryFactory",
    "AvailabilityRepository",
    "AvailabilityDayRepository",
    # "SlotManagerRepository",  # Removed - bitmap-only storage now
    "ConflictCheckerRepository",
    "BulkOperationRepository",
    "BookingRepository",
    "WeekOperationRepository",
    "InstructorProfileRepository",
    "SearchEventRepository",
    "ReferralCodeRepository",
    "ReferralClickRepository",
    "ReferralAttributionRepository",
    "ReferralRewardRepository",
    "WalletTransactionRepository",
    "ReferralLimitRepository",
]

# Version info
__version__ = "1.0.0"
