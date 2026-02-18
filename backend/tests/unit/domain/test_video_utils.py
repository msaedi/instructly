"""Tests for video domain utilities."""

import pytest

from app.domain.video_utils import compute_grace_minutes


@pytest.mark.unit
class TestComputeGraceMinutes:
    @pytest.mark.parametrize(
        "duration, expected",
        [
            (30, 7.5),  # 30 * 0.25 = 7.5 (under cap)
            (45, 11.25),  # 45 * 0.25 = 11.25 (under cap)
            (60, 15.0),  # 60 * 0.25 = 15 (hits cap exactly)
            (90, 15.0),  # 90 * 0.25 = 22.5 → capped at 15
            (120, 15.0),  # 120 * 0.25 = 30 → capped at 15
            (240, 15.0),  # 240 * 0.25 = 60 → capped at 15
        ],
    )
    def test_grace_minutes(self, duration: int, expected: float) -> None:
        assert compute_grace_minutes(duration) == expected
