"""Business day helpers for US federal holiday schedules."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Iterable

BUSINESS_WEEKDAYS = {0, 1, 2, 3, 4}


def _ensure_timezone(dt: datetime) -> None:
    """Raise if the provided datetime lacks timezone information."""

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("start_dt must be timezone-aware")


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the date of the nth occurrence of a weekday within a month."""

    if n <= 0:
        raise ValueError("n must be positive for nth weekday lookup")

    current = date(year, month, 1)
    count = 0
    while True:
        if current.weekday() == weekday:
            count += 1
            if count == n:
                return current
        current += timedelta(days=1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the date of the last given weekday within a month."""

    last_day = calendar.monthrange(year, month)[1]
    current = date(year, month, last_day)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _with_observed(days: Iterable[date]) -> set[date]:
    """Return observed holiday dates, expanding weekend dates to observed weekdays."""

    expanded: set[date] = set()
    for holiday in days:
        expanded.add(holiday)
        if holiday.weekday() == 5:  # Saturday -> observed Friday
            expanded.add(holiday - timedelta(days=1))
        elif holiday.weekday() == 6:  # Sunday -> observed Monday
            expanded.add(holiday + timedelta(days=1))
    return expanded


def us_federal_holidays(year: int) -> set[date]:
    """Return US federal holidays (actual + observed) for the provided year."""

    if year < 1900:
        raise ValueError("year must be >= 1900")

    holidays: list[date] = [
        date(year, 1, 1),  # New Year's Day
        _nth_weekday(year, 1, calendar.MONDAY, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, calendar.MONDAY, 3),  # Presidents' Day
        _last_weekday(year, 5, calendar.MONDAY),  # Memorial Day
        date(year, 6, 19),  # Juneteenth National Independence Day
        date(year, 7, 4),  # Independence Day
        _nth_weekday(year, 9, calendar.MONDAY, 1),  # Labor Day
        _nth_weekday(year, 10, calendar.MONDAY, 2),  # Indigenous Peoples' / Columbus Day
        date(year, 11, 11),  # Veterans Day
        _nth_weekday(year, 11, calendar.THURSDAY, 4),  # Thanksgiving Day
        date(year, 12, 25),  # Christmas Day
    ]

    return _with_observed(holidays)


def add_us_business_days(start_dt: datetime, n_days: int, holidays: set[date]) -> datetime:
    """Add US business days to a datetime, skipping weekends and holiday dates."""

    _ensure_timezone(start_dt)

    if n_days < 0:
        raise ValueError("n_days must be non-negative")

    if n_days == 0:
        return start_dt

    if holidays is None:
        raise ValueError("holidays set must be provided")

    remaining = n_days
    current = start_dt

    while remaining > 0:
        current += timedelta(days=1)
        current_date = current.date()
        if current.weekday() not in BUSINESS_WEEKDAYS:
            continue
        if current_date in holidays:
            continue
        remaining -= 1

    return current
