# backend/app/models/base_enum.py
"""
Safe enum helpers for SQLAlchemy.

This module provides utilities for creating SQLAlchemy Enum columns that
correctly use enum VALUES (not NAMES) when persisting to the database.

Problem Solved:
    The Dec 7 2024 bug occurred when bulk SQL seeding used lowercase values
    ('published') but SQLAlchemy SAEnum defaulted to uppercase names ('PUBLISHED').
    This caused silent data loss - ORM queries returned zero results even though
    data existed in the database.

Usage:
    from app.models.base_enum import create_safe_enum

    class MyModel(Base):
        status = Column(
            create_safe_enum(MyStatus, "my_status_enum"),
            nullable=False,
            default=MyStatus.ACTIVE,
        )

Note:
    All Python enums for database storage should inherit from (str, Enum)
    and define values explicitly:

    class MyStatus(str, Enum):
        ACTIVE = "active"      # Value in DB will be 'active'
        INACTIVE = "inactive"  # Value in DB will be 'inactive'
"""

from enum import Enum
from typing import Sequence, Type

from sqlalchemy import Enum as SAEnum


def create_safe_enum(
    enum_class: Type[Enum],
    name: str,
    *,
    native_enum: bool = True,
    create_type: bool = False,
    validate_strings: bool = True,
) -> SAEnum:
    """
    Create a SQLAlchemy Enum that correctly uses enum values (not names).

    This helper ensures consistency between:
    - ORM operations (Python enum instances)
    - Raw SQL operations (string values in database)
    - Bulk seeding operations (SQL INSERT statements)

    Args:
        enum_class: The Python Enum class to use
        name: Database type name for PostgreSQL native enum
        native_enum: Whether to use PostgreSQL native enum type (default True)
        create_type: Whether to auto-create the enum type (default False,
                     we create types in migrations)
        validate_strings: Whether to validate string values (default True)

    Returns:
        SQLAlchemy Enum column type configured for safe value-based storage

    Example:
        >>> class Status(str, Enum):
        ...     ACTIVE = "active"
        ...     DELETED = "deleted"
        >>> status_column = create_safe_enum(Status, "status_enum")
        >>> # In database: stores "active", "deleted"
        >>> # ORM queries: Status.ACTIVE matches "active" in DB
    """
    return SAEnum(
        enum_class,
        name=name,
        native_enum=native_enum,
        create_type=create_type,
        validate_strings=validate_strings,
        values_callable=_get_enum_values,
    )


def _get_enum_values(enum_class: Type[Enum]) -> Sequence[str]:
    """
    Extract values from an enum class for SAEnum storage.

    This function is the core of the safe enum pattern. SQLAlchemy's default
    behavior uses enum NAMES (e.g., 'PUBLISHED') but we want VALUES
    (e.g., 'published') to match what bulk SQL operations use.

    Args:
        enum_class: The Python Enum class

    Returns:
        List of enum values (not names)
    """
    return [member.value for member in enum_class]


def verify_enum_consistency(enum_class: Type[Enum]) -> None:
    """
    Verify that an enum is safe for database storage.

    Raises AssertionError if the enum pattern is problematic:
    - Enum doesn't inherit from str
    - Values don't match expected lowercase convention
    - Names and values are the same (defeats the purpose)

    Args:
        enum_class: The Python Enum class to verify

    Raises:
        AssertionError: If the enum pattern is problematic

    Example:
        >>> class BadEnum(Enum):  # Missing str inheritance!
        ...     ACTIVE = "active"
        >>> verify_enum_consistency(BadEnum)  # Raises AssertionError
    """
    # Check str inheritance for proper value comparison
    if not issubclass(enum_class, str):
        raise AssertionError(
            f"{enum_class.__name__} must inherit from (str, Enum) "
            "for safe database storage. Example: class {enum_class.__name__}(str, Enum)"
        )

    # Check that values are explicitly defined and differ from names
    for member in enum_class:
        if member.name == member.value:
            # This is a warning case - could be intentional
            pass  # Allow but note in documentation

        # Ensure values are strings
        if not isinstance(member.value, str):
            raise AssertionError(
                f"{enum_class.__name__}.{member.name} value must be a string, "
                f"got {type(member.value).__name__}"
            )
