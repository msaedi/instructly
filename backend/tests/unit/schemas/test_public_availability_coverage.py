"""Tests for app/schemas/public_availability.py — coverage gaps L157-159."""
from __future__ import annotations

from datetime import date

import pytest

from app.schemas.public_availability import PublicAvailabilityQuery


@pytest.mark.unit
class TestPublicAvailabilityQueryCoverage:
    """Cover the date_range_days property (L154-159)."""

    def test_date_range_days_no_end_date(self) -> None:
        """L157-158: when end_date is None, return 30."""
        query = PublicAvailabilityQuery(start_date=date(2025, 7, 1))
        assert query.date_range_days == 30

    def test_date_range_days_with_end_date(self) -> None:
        """L159: (end_date - start_date).days + 1."""
        query = PublicAvailabilityQuery(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 10),
        )
        assert query.date_range_days == 10

    def test_date_range_days_same_day(self) -> None:
        """start == end => 1 day."""
        query = PublicAvailabilityQuery(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 1),
        )
        assert query.date_range_days == 1

    def test_date_range_days_one_day_apart(self) -> None:
        query = PublicAvailabilityQuery(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 2),
        )
        assert query.date_range_days == 2

    def test_date_range_days_end_before_start(self) -> None:
        """Bug hunt: end_date < start_date gives negative/zero — no validation!"""
        query = PublicAvailabilityQuery(
            start_date=date(2025, 7, 10),
            end_date=date(2025, 7, 1),
        )
        # This returns -8 (negative) — potential bug in the schema
        assert query.date_range_days == -8
