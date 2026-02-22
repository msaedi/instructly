"""Tests for video domain utilities."""

import pytest

from app.domain.video_utils import compute_grace_minutes


@pytest.mark.unit
class TestComputeGraceMinutes:
    @pytest.mark.parametrize(
        "duration, expected",
        [
            (30, 7.5),  # min(7.5, 15) = 7.5
            (45, 11.25),  # min(11.25, 15) = 11.25
            (60, 15.0),  # min(15, 15) = 15
            (90, 15.0),  # min(22.5, 15) = 15
            (120, 15.0),  # min(30, 15) = 15
            (240, 15.0),  # min(60, 15) = 15
        ],
    )
    def test_grace_minutes(self, duration: int, expected: float) -> None:
        assert compute_grace_minutes(duration) == expected
