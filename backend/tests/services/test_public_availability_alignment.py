from __future__ import annotations

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from tests._utils.bitmap_avail import seed_day

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.availability_service import AvailabilityService
from app.services.config_service import ConfigService
from app.utils.bitset import (
    TAG_ONLINE_ONLY,
    bits_from_windows,
    new_empty_bits,
    new_empty_tags,
    set_range_tag,
)


def _instructor_tz(test_instructor) -> ZoneInfo:
    return ZoneInfo(getattr(test_instructor, "timezone", None) or "America/New_York")


def _service_without_init() -> AvailabilityService:
    service = AvailabilityService.__new__(AvailabilityService)
    service.db = MagicMock()
    service.logger = MagicMock()
    service.cache_service = None
    return service


class TestPublicAvailabilityBugHunt:
    def test_coerce_buffer_minutes_accepts_float_and_string_inputs(self) -> None:
        assert AvailabilityService._coerce_buffer_minutes(True, 15) == 15
        assert AvailabilityService._coerce_buffer_minutes(7.9, 15) == 7
        assert AvailabilityService._coerce_buffer_minutes("45", 15) == 45
        assert AvailabilityService._coerce_buffer_minutes("bad", 15) == 15
        assert AvailabilityService._coerce_buffer_minutes(object(), 15) == 15

    def test_merge_and_subtract_time_intervals_cover_gap_and_overlap_paths(self) -> None:
        merged = AvailabilityService._merge_time_intervals(
            [
                (time(9, 0), time(10, 0)),
                (time(9, 30), time(11, 0)),
                (time(12, 0), time(13, 0)),
            ]
        )
        assert merged == [
            (time(9, 0), time(11, 0)),
            (time(12, 0), time(13, 0)),
        ]

        assert AvailabilityService._subtract_time_intervals([], [(time(9, 0), time(10, 0))]) == []
        assert AvailabilityService._subtract_time_intervals(
            [(time(9, 0), time(12, 0))],
            [],
        ) == [(time(9, 0), time(12, 0))]

        subtracted = AvailabilityService._subtract_time_intervals(
            [
                (time(9, 0), time(12, 0)),
                (time(13, 0), time(15, 0)),
            ],
            [
                (time(10, 0), time(11, 0)),
                (time(14, 0), time(16, 0)),
            ],
        )
        assert subtracted == [
            (time(9, 0), time(10, 0)),
            (time(11, 0), time(12, 0)),
            (time(13, 0), time(14, 0)),
        ]

    def test_resolve_buffer_profile_values_handles_missing_profile_and_defaults(self) -> None:
        assert AvailabilityService._resolve_buffer_profile_values(
            None,
            default_non_travel_buffer_minutes=15,
            default_travel_buffer_minutes=60,
        ) == (15, 60)

        profile = SimpleNamespace(
            non_travel_buffer_minutes=True,
            travel_buffer_minutes=object(),
        )
        assert AvailabilityService._resolve_buffer_profile_values(
            profile,
            default_non_travel_buffer_minutes=15,
            default_travel_buffer_minutes=60,
        ) == (15, 60)

    def test_subtract_buffered_bookings_from_windows_handles_invalid_and_travel_buffers(
        self,
    ) -> None:
        assert AvailabilityService._subtract_buffered_bookings_from_windows(
            [],
            [],
            requested_location_type="online",
            non_travel_buffer_minutes=15,
            travel_buffer_minutes=60,
        ) == []

        non_travel_result = AvailabilityService._subtract_buffered_bookings_from_windows(
            [(time(9, 0), time(17, 0))],
            [
                SimpleNamespace(
                    start_time="09:00",
                    end_time=time(10, 0),
                    location_type="online",
                ),
                SimpleNamespace(
                    start_time=time(23, 0),
                    end_time=time(22, 0),
                    location_type="online",
                ),
                SimpleNamespace(
                    start_time=time(12, 0),
                    end_time=time(13, 0),
                    location_type="online",
                ),
            ],
            requested_location_type="online",
            non_travel_buffer_minutes=15,
            travel_buffer_minutes=60,
        )
        assert non_travel_result == [
            (time(9, 0), time(11, 45)),
            (time(13, 15), time(17, 0)),
        ]

        travel_result = AvailabilityService._subtract_buffered_bookings_from_windows(
            [(time(9, 0), time(17, 0))],
            [
                SimpleNamespace(
                    start_time=time(12, 0),
                    end_time=time(13, 0),
                    location_type="student_location",
                )
            ],
            requested_location_type="student_location",
            non_travel_buffer_minutes=15,
            travel_buffer_minutes=60,
        )
        assert travel_result == [
            (time(9, 0), time(11, 0)),
            (time(14, 0), time(17, 0)),
        ]

    def test_compute_public_availability_returns_empty_for_zero_bitmap_day(
        self,
        db,
        test_instructor,
    ) -> None:
        target_date = date.today() + timedelta(days=14)
        repo = AvailabilityDayRepository(db)
        repo.upsert_week(test_instructor.id, [(target_date, new_empty_bits())])
        db.commit()

        service = AvailabilityService(db)
        result = service.compute_public_availability(
            test_instructor.id,
            target_date,
            target_date,
            apply_min_advance=False,
        )

        assert result == {target_date.isoformat(): []}

    def test_filter_windows_by_format_tags_splits_middle_incompatible_segment(self) -> None:
        format_tags = set_range_tag(new_empty_tags(), 114, 6, TAG_ONLINE_ONLY)

        filtered = AvailabilityService._filter_windows_by_format_tags(
            [(time(9, 0), time(11, 0))],
            format_tags,
            requested_location_type="student_location",
        )

        assert filtered == [
            (time(9, 0), time(9, 30)),
            (time(10, 0), time(11, 0)),
        ]

    def test_filter_windows_by_format_tags_skips_incompatible_first_window_then_keeps_second(
        self,
    ) -> None:
        format_tags = set_range_tag(new_empty_tags(), 108, 12, TAG_ONLINE_ONLY)

        filtered = AvailabilityService._filter_windows_by_format_tags(
            [
                (time(9, 0), time(10, 0)),
                (time(10, 0), time(11, 0)),
            ],
            format_tags,
            requested_location_type="student_location",
        )

        assert filtered == [(time(10, 0), time(11, 0))]

    def test_load_public_availability_data_normalizes_tags_and_groups_bookings(self) -> None:
        target_date = date(2030, 1, 6)
        booking = SimpleNamespace(booking_date=target_date)
        bitmap_repo = MagicMock()
        bitmap_repo.get_days_in_range.return_value = [
            SimpleNamespace(
                day_date=target_date,
                bits=bits_from_windows([("09:00:00", "10:00:00")]),
                format_tags=None,
            )
        ]

        service = _service_without_init()
        service._bitmap_repo = MagicMock(return_value=bitmap_repo)
        service.conflict_repository = MagicMock()
        service.conflict_repository.get_bookings_for_date_range.return_value = [booking]

        by_date, tags_by_date, bookings_by_date = service._load_public_availability_data(
            "instructor-1",
            target_date,
            target_date,
        )

        assert by_date == {target_date: [(time(9, 0), time(10, 0))]}
        assert tags_by_date == {target_date: new_empty_tags()}
        assert bookings_by_date == {target_date: [booking]}

    def test_compute_public_availability_filters_past_day_before_earliest_allowed_date(
        self,
        db,
        test_instructor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        seed_day(db, test_instructor.id, yesterday, [("09:00", "17:00")])
        seed_day(db, test_instructor.id, today, [("09:00", "17:00")])
        seed_day(db, test_instructor.id, tomorrow, [("09:00", "17:00")])
        db.commit()

        fake_now = datetime.combine(today, time(12, 0), tzinfo=_instructor_tz(test_instructor))
        monkeypatch.setattr(
            "app.services.availability_service.get_user_now_by_id",
            lambda *_args, **_kwargs: fake_now,
        )
        monkeypatch.setattr(
            ConfigService,
            "get_advance_notice_minutes",
            lambda self, location_type=None: 60,
        )

        service = AvailabilityService(db)
        result = service.compute_public_availability(test_instructor.id, yesterday, tomorrow)

        assert result[yesterday.isoformat()] == []
        assert result[today.isoformat()] == [(time(13, 0), time(17, 0))]
        assert result[tomorrow.isoformat()] == [(time(9, 0), time(17, 0))]

    def test_compute_public_availability_applies_exact_24h_cutoff_with_15_minute_alignment(
        self,
        db,
        test_instructor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        seed_day(db, test_instructor.id, tomorrow, [("09:00", "12:00")])
        db.commit()

        fake_now = datetime.combine(today, time(9, 7), tzinfo=_instructor_tz(test_instructor))
        monkeypatch.setattr(
            "app.services.availability_service.get_user_now_by_id",
            lambda *_args, **_kwargs: fake_now,
        )
        monkeypatch.setattr(
            ConfigService,
            "get_advance_notice_minutes",
            lambda self, location_type=None: 24 * 60,
        )

        service = AvailabilityService(db)
        result = service.compute_public_availability(test_instructor.id, tomorrow, tomorrow)

        assert result[tomorrow.isoformat()] == [(time(9, 15), time(12, 0))]

    @pytest.mark.parametrize(
        ("slot_date", "start_time_str", "end_time_str"),
        [
            (date(2025, 3, 9), "01:30", "03:30"),
            (date(2025, 11, 2), "01:30", "02:30"),
        ],
    )
    def test_compute_public_availability_handles_dst_boundary_days(
        self,
        db,
        test_instructor,
        slot_date: date,
        start_time_str: str,
        end_time_str: str,
    ) -> None:
        seed_day(db, test_instructor.id, slot_date, [(start_time_str, end_time_str)])
        db.commit()

        service = AvailabilityService(db)
        result = service.compute_public_availability(
            test_instructor.id,
            slot_date,
            slot_date,
            apply_min_advance=False,
        )

        assert result[slot_date.isoformat()] == [
            (time.fromisoformat(start_time_str), time.fromisoformat(end_time_str))
        ]

    def test_trim_windows_for_advance_notice_skips_ended_windows_and_preserves_midnight_end(
        self,
    ) -> None:
        service = _service_without_init()

        trimmed = service._trim_windows_for_advance_notice(
            [
                (time(9, 0), time(10, 0)),
                (time(20, 0), time(0, 0)),
                (time(22, 0), time(23, 0)),
            ],
            21 * 60,
        )

        assert trimmed == [
            (time(21, 0), time(0, 0)),
            (time(22, 0), time(23, 0)),
        ]

    def test_resolve_earliest_allowed_booking_handles_disabled_and_missing_config(self) -> None:
        service = _service_without_init()
        service.config_service = MagicMock()
        service.config_service.get_advance_notice_minutes.return_value = 0

        assert service._resolve_earliest_allowed_booking(
            "instructor-1",
            requested_location_type="online",
            apply_min_advance=True,
        ) == (None, None)
        assert service._resolve_earliest_allowed_booking(
            "instructor-1",
            requested_location_type="online",
            apply_min_advance=False,
        ) == (None, None)

        service.config_service = None
        with pytest.raises(RuntimeError, match="Config service is required"):
            service._resolve_earliest_allowed_booking(
                "instructor-1",
                requested_location_type="online",
                apply_min_advance=True,
            )

    def test_windows_support_booking_request_rejects_ninety_minutes_when_only_sixty_available(
        self,
    ) -> None:
        supported = AvailabilityService._windows_support_booking_request(
            [(time(9, 0), time(10, 0))],
            duration_minutes=90,
        )

        assert supported is False

    def test_windows_support_booking_request_currently_accepts_unaligned_thirty_minute_window(
        self,
    ) -> None:
        # BUG: the helper only checks raw duration and ignores the 15-minute booking-start
        # contract, so a 09:05-09:35 window is treated as bookable for 30 minutes.
        supported = AvailabilityService._windows_support_booking_request(
            [(time(9, 5), time(9, 35))],
            duration_minutes=30,
        )

        assert supported is True

    def test_compute_public_availability_requires_config_service(self, db) -> None:
        service = AvailabilityService(db)
        service.config_service = None

        with pytest.raises(RuntimeError, match="Config service is required"):
            service.compute_public_availability(
                "instructor-1",
                date.today(),
                date.today(),
            )
