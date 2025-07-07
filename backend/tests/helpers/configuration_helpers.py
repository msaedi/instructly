# backend/tests/helpers/configuration_helpers.py
"""
Helper functions and fixtures for overriding configuration in tests.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.core.config import settings


@contextmanager
def override_public_api_config(detail_level=None, days=None, show_instructor_name=None, cache_ttl=None):
    """
    Context manager to temporarily override public API configuration.

    Usage:
        with override_public_api_config(detail_level="full", days=30):
            # Your test code here
    """
    patches = []

    if detail_level is not None:
        patches.append(patch.object(settings, "public_availability_detail_level", detail_level))

    if days is not None:
        patches.append(patch.object(settings, "public_availability_days", days))

    if show_instructor_name is not None:
        patches.append(patch.object(settings, "public_availability_show_instructor_name", show_instructor_name))

    if cache_ttl is not None:
        patches.append(patch.object(settings, "public_availability_cache_ttl", cache_ttl))

    # Start all patches
    for p in patches:
        p.start()

    try:
        yield
    finally:
        # Stop all patches
        for p in patches:
            p.stop()


@pytest.fixture
def force_full_detail():
    """Fixture to force full detail level for a test."""
    with override_public_api_config(detail_level="full"):
        yield


@pytest.fixture
def force_summary_detail():
    """Fixture to force summary detail level for a test."""
    with override_public_api_config(detail_level="summary"):
        yield


@pytest.fixture
def force_minimal_detail():
    """Fixture to force minimal detail level for a test."""
    with override_public_api_config(detail_level="minimal"):
        yield


def assert_full_detail_response(response_data, expected_days=None):
    """Assert that response has full detail structure."""
    assert "availability_by_date" in response_data
    assert "total_available_slots" in response_data
    assert "earliest_available_date" in response_data

    if expected_days is not None:
        assert len(response_data["availability_by_date"]) == expected_days


def assert_summary_detail_response(response_data):
    """Assert that response has summary detail structure."""
    assert "availability_summary" in response_data
    assert "detail_level" in response_data
    assert response_data["detail_level"] == "summary"
    assert "total_available_days" in response_data


def assert_minimal_detail_response(response_data):
    """Assert that response has minimal detail structure."""
    assert "has_availability" in response_data
    assert "earliest_available_date" in response_data
    # Should NOT have detailed data
    assert "availability_by_date" not in response_data
    assert "availability_summary" not in response_data
