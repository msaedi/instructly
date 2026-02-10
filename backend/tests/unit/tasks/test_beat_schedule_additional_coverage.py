from __future__ import annotations

from app.tasks import beat_schedule


def test_parse_cron_expression_falls_back_on_invalid_expression(caplog) -> None:
    with caplog.at_level("WARNING"):
        schedule = beat_schedule._parse_cron_expression("invalid cron")

    assert getattr(schedule, "_orig_minute") == "0"
    assert getattr(schedule, "_orig_hour") == "4"
    assert "Invalid RETENTION_PURGE_CRON expression" in caplog.text


def test_parse_cron_expression_uses_supplied_parts() -> None:
    schedule = beat_schedule._parse_cron_expression("15 2 * * 1")

    assert getattr(schedule, "_orig_minute") == "15"
    assert getattr(schedule, "_orig_hour") == "2"
    assert getattr(schedule, "_orig_day_of_week") == "1"
