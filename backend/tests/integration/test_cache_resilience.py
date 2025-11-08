from __future__ import annotations

from unittest.mock import Mock

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.availability_service import AvailabilityService
from app.utils.bitset import bits_from_windows
from tests.utils.availability_builders import future_week_start


def test_week_get_falls_back_when_cache_failures_occur(db, test_instructor) -> None:
    """Cache errors should not prevent availability from loading."""

    week_start = future_week_start()
    repo = AvailabilityDayRepository(db)
    repo.upsert_week(
        test_instructor.id,
        [(week_start, bits_from_windows([("09:00:00", "10:00:00")]))],
    )
    db.commit()

    service = AvailabilityService(db)

    key_builder = Mock()
    key_builder.build.side_effect = lambda *parts: ":".join(str(p) for p in parts)

    cache_mock = Mock()
    cache_mock.key_builder = key_builder
    cache_mock.TTL_TIERS = {"warm": 3600, "hot": 1800}
    cache_mock.get_json.side_effect = [RuntimeError("cache miss"), None]
    cache_mock.set_json.side_effect = [RuntimeError("persist failed"), None]
    service.cache_service = cache_mock

    result = service.get_week_availability(test_instructor.id, week_start)
    assert result[week_start.isoformat()][0]["start_time"] == "09:00:00"
    assert cache_mock.get_json.call_count >= 1
    assert cache_mock.set_json.call_count >= 1
