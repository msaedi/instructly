"""Tests for ServiceFormatPrice model constraints and cascade behavior."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.instructor import InstructorProfile
from app.models.service_catalog import (
    InstructorService,
    ServiceCatalog,
    ServiceCategory,
    ServiceFormatPrice,
)
from app.models.subcategory import ServiceSubcategory
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_instructor_service(db) -> InstructorService:
    """Create a minimal User → InstructorProfile → InstructorService chain."""
    user = User(
        id="u-fmt-test",
        email="fmt-test@example.com",
        hashed_password="hashed",
        first_name="Fmt",
        last_name="Tester",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(id="u-fmt-test", user_id="u-fmt-test")
    db.add(profile)
    db.flush()

    category = ServiceCategory(id="cat-fmt", name="Music", display_order=0)
    db.add(category)
    db.flush()

    subcategory = ServiceSubcategory(
        id="sub-fmt", category_id="cat-fmt", name="Instruments", display_order=0
    )
    db.add(subcategory)
    db.flush()

    catalog = ServiceCatalog(
        id="svc-fmt",
        subcategory_id="sub-fmt",
        name="Piano",
        slug="piano-fmt",
        is_active=True,
    )
    db.add(catalog)
    db.flush()

    service = InstructorService(
        id="is-fmt",
        instructor_profile_id="u-fmt-test",
        service_catalog_id="svc-fmt",
        is_active=True,
    )
    db.add(service)
    db.flush()

    # Add format prices
    db.add(ServiceFormatPrice(service_id="is-fmt", format="online", hourly_rate=Decimal("100.00")))
    db.add(
        ServiceFormatPrice(
            service_id="is-fmt", format="student_location", hourly_rate=Decimal("120.00")
        )
    )
    db.flush()

    return service


# ---------------------------------------------------------------------------
# 1. Cascade delete test
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_delete_service_cascades_to_format_prices(unit_db):
    """Deleting an InstructorService cascades to its ServiceFormatPrice children."""
    db = unit_db
    service = _setup_instructor_service(db)
    service_id = service.id

    # Verify prices exist
    prices_before = (
        db.query(ServiceFormatPrice).filter(ServiceFormatPrice.service_id == service_id).all()
    )
    assert len(prices_before) == 2

    # Delete the service
    db.delete(service)
    db.flush()

    # Verify prices are gone
    prices_after = (
        db.query(ServiceFormatPrice).filter(ServiceFormatPrice.service_id == service_id).all()
    )
    assert len(prices_after) == 0


# ---------------------------------------------------------------------------
# 2. Boundary value tests (CHECK constraints)
# ---------------------------------------------------------------------------
# NOTE: SQLite doesn't enforce CHECK constraints, so these tests verify the
# ORM layer accepts boundary values. The CHECK constraints are enforced by
# PostgreSQL in integration/production.


@pytest.mark.unit
def test_rate_exactly_1000_accepted(unit_db):
    """$1000.00 is the maximum allowed rate."""
    db = unit_db
    _setup_instructor_service(db)

    # Use a different format so we don't violate UNIQUE on (service_id, format)
    price = ServiceFormatPrice(
        service_id="is-fmt",
        format="instructor_location",
        hourly_rate=Decimal("1000.00"),
    )
    db.add(price)
    db.flush()

    fetched = db.query(ServiceFormatPrice).filter(ServiceFormatPrice.id == price.id).one()
    assert fetched.hourly_rate == Decimal("1000.00")


@pytest.mark.unit
def test_rate_exactly_001_accepted(unit_db):
    """$0.01 is the minimum non-zero rate."""
    db = unit_db
    _setup_instructor_service(db)

    price = ServiceFormatPrice(
        service_id="is-fmt",
        format="instructor_location",
        hourly_rate=Decimal("0.01"),
    )
    db.add(price)
    db.flush()

    fetched = db.query(ServiceFormatPrice).filter(ServiceFormatPrice.id == price.id).one()
    assert fetched.hourly_rate == Decimal("0.01")
