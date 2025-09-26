# backend/app/models/types.py
"""
Custom SQLAlchemy types that work across different database backends.
"""

from datetime import datetime
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Integer, String, TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from sqlalchemy.sql import func

# Base class for all models
Base = declarative_base()

if TYPE_CHECKING:
    from sqlalchemy.sql.type_api import TypeDecorator as _TypeDecorator

    TypeDecoratorProtocol = _TypeDecorator[Any]
else:
    TypeDecoratorProtocol = TypeDecorator


class TimestampMixin:
    """Mixin class for automatic timestamp tracking."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )


class ArrayType(TypeDecoratorProtocol):
    """
    A custom type that uses PostgreSQL ARRAY when available,
    but falls back to JSON serialization for other databases (like SQLite).
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Integer))
        else:
            return dialect.type_descriptor(String(255))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return json.dumps(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return json.loads(value)


class IntegerArrayType(TypeDecoratorProtocol):
    """
    A custom type for integer arrays that works across different database backends.
    Uses PostgreSQL ARRAY when available, falls back to JSON for others.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Integer))
        else:
            return dialect.type_descriptor(String(255))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        # Ensure we have a list of integers
        if isinstance(value, (list, tuple)):
            return json.dumps([int(v) for v in value])
        return json.dumps([int(value)])

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value


class StringArrayType(TypeDecoratorProtocol):
    """
    A custom type for string arrays that works across different database backends.
    Uses PostgreSQL ARRAY when available, falls back to JSON for others.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        else:
            return dialect.type_descriptor(String(1024))  # Larger size for string arrays

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        # Ensure we have a list of strings
        if isinstance(value, (list, tuple)):
            return json.dumps([str(v) for v in value])
        return json.dumps([str(value)])

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value
