from datetime import datetime, timezone

import pytest

from app.utils.business_days import add_us_business_days, us_federal_holidays


def _holidays_for_years(*years: int) -> set:
    holidays: set = set()
    for year in years:
        holidays |= us_federal_holidays(year)
    return holidays


def test_adds_five_business_days_midweek():
    start = datetime(2024, 3, 6, 10, 30, tzinfo=timezone.utc)  # Wednesday
    holidays = _holidays_for_years(2024)

    result = add_us_business_days(start, 5, holidays)

    assert result == datetime(2024, 3, 13, 10, 30, tzinfo=timezone.utc)


def test_adds_five_business_days_from_friday():
    start = datetime(2024, 3, 8, 18, 0, tzinfo=timezone.utc)  # Friday
    holidays = _holidays_for_years(2024)

    result = add_us_business_days(start, 5, holidays)

    assert result == datetime(2024, 3, 15, 18, 0, tzinfo=timezone.utc)


def test_skips_weekend_and_observed_independence_day():
    start = datetime(2021, 6, 28, 9, 0, tzinfo=timezone.utc)
    holidays = _holidays_for_years(2021)

    result = add_us_business_days(start, 5, holidays)

    assert result == datetime(2021, 7, 6, 9, 0, tzinfo=timezone.utc)


def test_cross_year_window_handles_new_year_observed():
    start = datetime(2023, 12, 29, 12, 0, tzinfo=timezone.utc)
    holidays = _holidays_for_years(2023, 2024)

    result = add_us_business_days(start, 3, holidays)

    assert result == datetime(2024, 1, 4, 12, 0, tzinfo=timezone.utc)


def test_rejects_naive_datetime():
    holidays = _holidays_for_years(2024)

    with pytest.raises(ValueError):
        add_us_business_days(datetime(2024, 3, 6, 10, 30), 1, holidays)


def test_rejects_negative_days():
    start = datetime(2024, 3, 6, 10, 30, tzinfo=timezone.utc)
    holidays = _holidays_for_years(2024)

    with pytest.raises(ValueError):
        add_us_business_days(start, -1, holidays)


@pytest.mark.parametrize("invalid_year", [1899, 1500])
def test_holiday_year_validation(invalid_year: int):
    with pytest.raises(ValueError):
        us_federal_holidays(invalid_year)
