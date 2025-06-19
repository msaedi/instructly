# backend/app/api/dependencies/database.py
"""
Database-related dependencies.
"""

from typing import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ...database import get_db as original_get_db


def get_db() -> Generator[Session, None, None]:
    """
    Get database session dependency.

    Yields:
        Database session that will be closed after use
    """
    yield from original_get_db()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session dependency.

    For future use when we migrate to async SQLAlchemy.

    Yields:
        Async database session
    """
    # Placeholder for async implementation
    raise NotImplementedError("Async database not yet implemented")
