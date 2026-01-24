import pytest

from app.utils.time_utils import minutes_to_time_str


def test_minutes_to_time_str_invalid_minutes_raise() -> None:
    with pytest.raises(ValueError, match="minutes out of range"):
        minutes_to_time_str(-1)
