"""Tests for week operation service, specifically empty source week guard."""

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.week_operation_service import WeekOperationService
from app.utils.bitset import bits_from_windows


@pytest.fixture
def week_operation_service(db: Session):
    """Create a WeekOperationService instance."""
    return WeekOperationService(db)


@pytest.mark.skipif(
    not __import__("os").getenv("AVAILABILITY_V2_BITMAPS", "0").lower() in {"1", "true", "yes"},
    reason="Bitmap v2 not enabled",
)
def test_copy_week_availability_empty_source_week_guard(
    db: Session, test_instructor: User, week_operation_service: WeekOperationService
):
    """Test that copying from an empty source week returns 0 without writing."""
    instructor_id = test_instructor.id

    # Create an empty source week (no bitmap rows, or all zero bits)
    from_week_start = date.today() - timedelta(days=date.today().weekday())  # Monday of current week
    to_week_start = from_week_start + timedelta(days=7)  # Next Monday

    # Ensure source week has no bitmap rows (or explicitly set empty bits)
    repo = AvailabilityDayRepository(db)
    # Don't create any rows - source week should be empty

    # Verify target week also has no rows initially
    target_bits_before = repo.get_week_rows(instructor_id, to_week_start)
    assert len(target_bits_before) == 0

    # Attempt copy
    import asyncio
    result = asyncio.run(
        week_operation_service.copy_week_availability(
            instructor_id=instructor_id,
            from_week_start=from_week_start,
            to_week_start=to_week_start,
        )
    )

    # Should return 0-copy result
    assert result["_metadata"]["slots_created"] == 0
    assert "no availability bits" in result["_metadata"]["message"].lower()

    # Verify target week still has no rows
    target_bits_after = repo.get_week_rows(instructor_id, to_week_start)
    assert len(target_bits_after) == 0


@pytest.mark.skipif(
    not __import__("os").getenv("AVAILABILITY_V2_BITMAPS", "0").lower() in {"1", "true", "yes"},
    reason="Bitmap v2 not enabled",
)
def test_copy_week_availability_with_non_empty_source(
    db: Session, test_instructor: User, week_operation_service: WeekOperationService
):
    """Test that copying from a non-empty source week works normally."""
    instructor_id = test_instructor.id

    from_week_start = date.today() - timedelta(days=date.today().weekday())  # Monday
    to_week_start = from_week_start + timedelta(days=7)  # Next Monday

    # Create source week with availability bits
    repo = AvailabilityDayRepository(db)
    windows = [("10:00:00", "12:00:00")]
    bits = bits_from_windows(windows)

    # Set availability for Monday-Wednesday of source week
    entries = []
    for offset in range(3):
        day = from_week_start + timedelta(days=offset)
        entries.append((day, bits))
    repo.upsert_week(instructor_id, entries)
    db.commit()

    # Verify source week has bits
    source_bits = repo.get_week_rows(instructor_id, from_week_start)
    assert len(source_bits) >= 3

    # Attempt copy
    import asyncio
    result = asyncio.run(
        week_operation_service.copy_week_availability(
            instructor_id=instructor_id,
            from_week_start=from_week_start,
            to_week_start=to_week_start,
        )
    )

    # Should copy successfully
    assert result["_metadata"]["slots_created"] > 0

    # Verify target week received the bits
    target_bits_after = repo.get_week_rows(instructor_id, to_week_start)
    assert len(target_bits_after) >= 3
