"""Tests for ServiceFormatPrice model constraints and cascade behavior."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.exceptions import BusinessRuleException
from app.models.instructor import InstructorProfile
from app.models.service_catalog import (
    SERVICE_PRICE_FORMAT_ORDER,
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


# ---------------------------------------------------------------------------
# 3. hourly_rate_for_location_type — missing format edge case
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hourly_rate_for_location_type_missing_format(unit_db):
    """hourly_rate_for_location_type raises when requested format is not configured."""
    db = unit_db
    service = _setup_instructor_service(db)
    # service has only 'online' and 'student_location' — no 'instructor_location'

    with pytest.raises(BusinessRuleException, match="No pricing configured"):
        service.hourly_rate_for_location_type("instructor_location")


# ---------------------------------------------------------------------------
# 4. serialized_format_prices maintains SERVICE_PRICE_FORMAT_ORDER
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_serialized_format_prices_respects_order(unit_db):
    """serialized_format_prices returns rows in SERVICE_PRICE_FORMAT_ORDER."""
    db = unit_db
    service = _setup_instructor_service(db)

    # Add instructor_location so all 3 formats are present
    db.add(
        ServiceFormatPrice(
            service_id="is-fmt",
            format="instructor_location",
            hourly_rate=Decimal("110.00"),
        )
    )
    db.flush()
    # Refresh to pick up the new row
    db.refresh(service)
    service._invalidate_price_cache()

    serialized = service.serialized_format_prices
    formats = [entry["format"] for entry in serialized]

    # Must match the canonical order defined by SERVICE_PRICE_FORMAT_ORDER
    expected = [f for f in SERVICE_PRICE_FORMAT_ORDER if f in formats]
    assert formats == expected


# ---------------------------------------------------------------------------
# 5. _coerce_format_price_row — invalid inputs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_coerce_format_price_row_rejects_dict_missing_hourly_rate(unit_db):
    """Dict without hourly_rate raises ValueError."""
    db = unit_db
    service = _setup_instructor_service(db)

    with pytest.raises(ValueError, match="hourly_rate"):
        service._coerce_format_price_row("format_prices", {"format": "online"})


@pytest.mark.unit
def test_coerce_format_price_row_rejects_non_dict_non_model(unit_db):
    """Non-dict, non-ServiceFormatPrice input raises TypeError."""
    db = unit_db
    service = _setup_instructor_service(db)

    with pytest.raises(TypeError, match="ServiceFormatPrice or dict"):
        service._coerce_format_price_row("format_prices", "invalid")


@pytest.mark.unit
def test_coerce_format_price_row_rejects_empty_format(unit_db):
    """Dict with empty-string format raises ValueError."""
    db = unit_db
    service = _setup_instructor_service(db)

    with pytest.raises(ValueError, match="non-empty format"):
        service._coerce_format_price_row(
            "format_prices", {"format": "", "hourly_rate": 100}
        )
