# backend/app/repositories/__init__.py
"""
Repository Pattern Implementation for InstaInstru Platform

This package provides the repository layer for data access,
separating business logic from database queries.

Key Components:
- BaseRepository: Foundation for all repositories
- IRepository: Interface defining required methods
- RepositoryFactory: Factory for creating repository instances

Usage:
    from app.repositories import BaseRepository, RepositoryFactory

    # In a service:
    repository = RepositoryFactory.create_availability_repository(db)
    availability = repository.get_by_date(instructor_id, date)
"""

from .base_repository import BaseRepository, IRepository
from .factory import RepositoryFactory

__all__ = [
    "BaseRepository",
    "IRepository",
    "RepositoryFactory",
]

# Version info
__version__ = "1.0.0"
