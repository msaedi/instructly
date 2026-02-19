"""Tests for video domain utilities."""

import pytest

from app.domain.video_utils import compute_grace_minutes


@pytest.mark.unit
class TestComputeGraceMinutes:
    # TESTING-ONLY: revert before production (original values in comments)
    @pytest.mark.parametrize(
        "duration, expected",
        [
            (30, 25),  # max(30-5, 7.5) = 25  (was 7.5)
            (45, 40),  # max(45-5, 11.25) = 40  (was 11.25)
            (60, 55),  # max(60-5, 15) = 55  (was 15.0)
            (90, 85),  # max(90-5, 22.5) = 85  (was 15.0)
            (120, 115),  # max(120-5, 30) = 115  (was 15.0)
            (240, 235),  # max(240-5, 60) = 235  (was 15.0)
        ],
    )
    def test_grace_minutes(self, duration: int, expected: float) -> None:
        assert compute_grace_minutes(duration) == expected
