"""Tests for ServiceFormatPricingRepository.sync_format_prices."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.exceptions import RepositoryException
from app.models.instructor import InstructorProfile
from app.models.service_catalog import (
    InstructorService,
    ServiceCatalog,
    ServiceCategory,
    ServiceFormatPrice,
)
from app.models.subcategory import ServiceSubcategory
from app.models.user import User
from app.repositories.service_format_pricing_repository import ServiceFormatPricingRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_service_with_prices(db) -> str:
    """Create a full chain and return the InstructorService ID."""
    user = User(
        id="u-repo-fmt",
        email="repo-fmt@example.com",
        hashed_password="hashed",
        first_name="Repo",
        last_name="Tester",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(id="u-repo-fmt", user_id="u-repo-fmt")
    db.add(profile)
    db.flush()

    category = ServiceCategory(id="cat-repo-fmt", name="Music", display_order=0)
    db.add(category)
    db.flush()

    subcategory = ServiceSubcategory(
        id="sub-repo-fmt", category_id="cat-repo-fmt", name="Instruments", display_order=0
    )
    db.add(subcategory)
    db.flush()

    catalog = ServiceCatalog(
        id="svc-repo-fmt",
        subcategory_id="sub-repo-fmt",
        name="Piano",
        slug="piano-repo-fmt",
        is_active=True,
    )
    db.add(catalog)
    db.flush()

    service = InstructorService(
        id="is-repo-fmt",
        instructor_profile_id="u-repo-fmt",
        service_catalog_id="svc-repo-fmt",
        is_active=True,
    )
    db.add(service)
    db.flush()

    # Seed initial prices
    db.add(ServiceFormatPrice(service_id="is-repo-fmt", format="online", hourly_rate=Decimal("80.00")))
    db.add(
        ServiceFormatPrice(
            service_id="is-repo-fmt", format="student_location", hourly_rate=Decimal("100.00")
        )
    )
    db.flush()

    return service.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sync_format_prices_replaces_existing(unit_db):
    """Sync deletes old prices and inserts new ones atomically."""
    db = unit_db
    service_id = _setup_service_with_prices(db)
    repo = ServiceFormatPricingRepository(db)

    # Verify initial state
    old_prices = repo.get_prices_for_service(service_id)
    assert len(old_prices) == 2
    old_formats = {p.format for p in old_prices}
    assert old_formats == {"online", "student_location"}

    # Sync with completely new prices
    new_prices = [
        {"format": "instructor_location", "hourly_rate": Decimal("150.00")},
        {"format": "online", "hourly_rate": Decimal("90.00")},
    ]
    result = repo.sync_format_prices(service_id, new_prices)

    # Old prices should be gone, new ones present
    current_prices = repo.get_prices_for_service(service_id)
    assert len(current_prices) == 2
    current_map = {p.format: p.hourly_rate for p in current_prices}
    assert "student_location" not in current_map
    assert current_map["instructor_location"] == Decimal("150.00")
    assert current_map["online"] == Decimal("90.00")

    # Return value should match
    assert len(result) == 2


@pytest.mark.unit
def test_sync_format_prices_rejects_empty_list(unit_db):
    """Empty price list raises RepositoryException."""
    db = unit_db
    service_id = _setup_service_with_prices(db)
    repo = ServiceFormatPricingRepository(db)

    with pytest.raises(RepositoryException, match="at least one format"):
        repo.sync_format_prices(service_id, prices=[])
