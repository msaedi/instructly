# backend/app/models/types.py
"""
Custom SQLAlchemy types that work across different database backends.
"""

import json

from sqlalchemy import String, TypeDecorator
from sqlalchemy.dialects.postgresql import ARRAY


class ArrayType(TypeDecorator):
    """
    A custom type that uses PostgreSQL ARRAY when available,
    but falls back to JSON serialization for other databases (like SQLite).
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Integer))
        else:
            return dialect.type_descriptor(String(255))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return json.loads(value)


from sqlalchemy import Integer


class IntegerArrayType(TypeDecorator):
    """
    A custom type for integer arrays that works across different database backends.
    Uses PostgreSQL ARRAY when available, falls back to JSON for others.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Integer))
        else:
            return dialect.type_descriptor(String(255))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        # Ensure we have a list of integers
        if isinstance(value, (list, tuple)):
            return json.dumps([int(v) for v in value])
        return json.dumps([int(value)])

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value


class StringArrayType(TypeDecorator):
    """
    A custom type for string arrays that works across different database backends.
    Uses PostgreSQL ARRAY when available, falls back to JSON for others.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        else:
            return dialect.type_descriptor(String(1024))  # Larger size for string arrays

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        # Ensure we have a list of strings
        if isinstance(value, (list, tuple)):
            return json.dumps([str(v) for v in value])
        return json.dumps([str(value)])

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value
