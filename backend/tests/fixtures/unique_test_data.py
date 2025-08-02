"""
Unique test data generation using UUIDs to prevent test conflicts.

This ensures each test run creates unique data that won't conflict
with other tests, solving the isolation problem without complex
transaction handling.
"""

import uuid
from typing import Any, Dict


class UniqueTestData:
    """Generate unique test data for each test run."""

    @staticmethod
    def unique_email(base: str = "test") -> str:
        """Generate a unique email address."""
        unique_id = str(uuid.uuid4())[:8]
        return f"{base}.{unique_id}@example.com"

    @staticmethod
    def unique_name(base: str = "Test") -> str:
        """Generate a unique name."""
        unique_id = str(uuid.uuid4())[:8]
        return f"{base} {unique_id}"

    @staticmethod
    def unique_service_name(base: str = "Service") -> str:
        """Generate a unique service name."""
        unique_id = str(uuid.uuid4())[:8]
        return f"{base} {unique_id}"

    @staticmethod
    def unique_category_name(base: str = "Category") -> str:
        """Generate a unique category name."""
        unique_id = str(uuid.uuid4())[:8]
        return f"{base} {unique_id}"

    @staticmethod
    def unique_slug(base: str = "slug") -> str:
        """Generate a unique slug."""
        unique_id = str(uuid.uuid4())[:8]
        return f"{base}-{unique_id}"


# Singleton instance for easy import
unique_data = UniqueTestData()
