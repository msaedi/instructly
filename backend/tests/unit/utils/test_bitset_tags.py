from __future__ import annotations

import pytest

from app.core.constants import (
    SLOTS_PER_DAY,
    TAG_NO_TRAVEL,
    TAG_NONE,
    TAG_ONLINE_ONLY,
    TAG_RESERVED,
)
from app.utils.bitset import (
    get_range_tag,
    get_slot_tag,
    is_tag_compatible,
    new_empty_tags,
    set_range_tag,
    set_slot_tag,
)


@pytest.mark.parametrize("slot", [0, 111, 287])
@pytest.mark.parametrize("tag", [TAG_NONE, TAG_ONLINE_ONLY, TAG_NO_TRAVEL, TAG_RESERVED])
def test_set_slot_tag_round_trip(slot: int, tag: int) -> None:
    tags = new_empty_tags()
    updated = set_slot_tag(tags, slot, tag)
    assert get_slot_tag(updated, slot) == tag


def test_set_and_get_range_tag_round_trip() -> None:
    tags = set_range_tag(new_empty_tags(), 60, 6, TAG_NO_TRAVEL)
    assert get_range_tag(tags, 60, 6) == TAG_NO_TRAVEL


def test_get_range_tag_returns_none_for_mixed_range() -> None:
    tags = set_range_tag(new_empty_tags(), 30, 6, TAG_ONLINE_ONLY)
    tags = set_slot_tag(tags, 33, TAG_NONE)
    assert get_range_tag(tags, 30, 6) is None


@pytest.mark.parametrize(
    ("tag", "location_type", "expected"),
    [
        (TAG_NONE, "online", True),
        (TAG_NONE, "instructor_location", True),
        (TAG_NONE, "student_location", True),
        (TAG_NONE, "neutral_location", True),
        (TAG_ONLINE_ONLY, "online", True),
        (TAG_ONLINE_ONLY, "instructor_location", False),
        (TAG_ONLINE_ONLY, "student_location", False),
        (TAG_ONLINE_ONLY, "neutral_location", False),
        (TAG_NO_TRAVEL, "online", True),
        (TAG_NO_TRAVEL, "instructor_location", True),
        (TAG_NO_TRAVEL, "student_location", False),
        (TAG_NO_TRAVEL, "neutral_location", False),
        (TAG_RESERVED, "online", False),
        (TAG_RESERVED, "instructor_location", False),
        (TAG_RESERVED, "student_location", False),
        (TAG_RESERVED, "neutral_location", False),
    ],
)
def test_is_tag_compatible_truth_table(tag: int, location_type: str, expected: bool) -> None:
    assert is_tag_compatible(tag, location_type) is expected


def test_get_slot_tag_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="tags length must be"):
        get_slot_tag(b"\x00" * 71, 0)


def test_get_slot_tag_rejects_out_of_range_slot() -> None:
    with pytest.raises(ValueError, match="slot out of range"):
        get_slot_tag(new_empty_tags(), SLOTS_PER_DAY)


@pytest.mark.parametrize(
    ("start_slot", "count"),
    [
        (-1, 6),
        (0, 0),
        (0, -1),
        (SLOTS_PER_DAY - 3, 6),
    ],
)
def test_set_range_tag_rejects_out_of_bounds_ranges(start_slot: int, count: int) -> None:
    with pytest.raises(ValueError):
        set_range_tag(new_empty_tags(), start_slot, count, TAG_ONLINE_ONLY)
