"""Integration tests for service_format_pricing database constraints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.service_catalog import InstructorService, ServiceFormatPrice

pytestmark = pytest.mark.integration


def _get_instructor_service(db) -> InstructorService:
    """Retrieve an existing instructor service from the test DB."""
    svc = db.query(InstructorService).first()
    if svc is None:
        raise RuntimeError("No InstructorService found — ensure test_instructor fixture has run")
    return svc


def test_db_unique_constraint_rejects_duplicate_formats(db, test_instructor):
    """UNIQUE(service_id, format) rejects duplicate format for same service."""
    svc = _get_instructor_service(db)

    # The test_instructor fixture already seeds format_prices for this service.
    # Find a format that already exists.
    existing = (
        db.query(ServiceFormatPrice)
        .filter(ServiceFormatPrice.service_id == svc.id)
        .first()
    )
    assert existing is not None, "Expected at least one format price from fixture"

    duplicate = ServiceFormatPrice(
        service_id=svc.id,
        format=existing.format,
        hourly_rate=Decimal("50.00"),
    )
    db.add(duplicate)

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()


def test_db_check_constraint_rejects_rate_above_cap(db, test_instructor):
    """CHECK(hourly_rate <= 1000) rejects rates above $1000."""
    svc = _get_instructor_service(db)

    # Delete any existing 'online' row so the unique constraint doesn't interfere.
    db.query(ServiceFormatPrice).filter(
        ServiceFormatPrice.service_id == svc.id,
        ServiceFormatPrice.format == "online",
    ).delete()
    db.flush()

    over_cap = ServiceFormatPrice(
        service_id=svc.id,
        format="online",
        hourly_rate=Decimal("1500.00"),
    )
    db.add(over_cap)

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()


def test_db_check_constraint_rejects_zero_rate(db, test_instructor):
    """CHECK(hourly_rate > 0) rejects zero rate."""
    svc = _get_instructor_service(db)

    db.query(ServiceFormatPrice).filter(
        ServiceFormatPrice.service_id == svc.id,
        ServiceFormatPrice.format == "online",
    ).delete()
    db.flush()

    zero_rate = ServiceFormatPrice(
        service_id=svc.id,
        format="online",
        hourly_rate=Decimal("0.00"),
    )
    db.add(zero_rate)

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()


def test_db_check_constraint_rejects_negative_rate(db, test_instructor):
    """CHECK(hourly_rate > 0) rejects negative rate."""
    svc = _get_instructor_service(db)

    db.query(ServiceFormatPrice).filter(
        ServiceFormatPrice.service_id == svc.id,
        ServiceFormatPrice.format == "online",
    ).delete()
    db.flush()

    negative_rate = ServiceFormatPrice(
        service_id=svc.id,
        format="online",
        hourly_rate=Decimal("-10.00"),
    )
    db.add(negative_rate)

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()


def test_db_check_constraint_rejects_invalid_format(db, test_instructor):
    """CHECK(format IN (...)) rejects unknown format strings."""
    svc = _get_instructor_service(db)

    invalid = ServiceFormatPrice(
        service_id=svc.id,
        format="invalid_format",
        hourly_rate=Decimal("50.00"),
    )
    db.add(invalid)

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()
