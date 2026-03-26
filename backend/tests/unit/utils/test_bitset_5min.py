import pytest

from app.utils.bitset import (
    BYTES_PER_DAY,
    SLOTS_PER_DAY,
    bits_from_windows,
    new_empty_bits,
    pack_indexes,
    toggle_index,
    unpack_indexes,
    windows_from_bits,
)


def test_constants() -> None:
    assert SLOTS_PER_DAY == 288
    assert BYTES_PER_DAY == 36


def test_new_empty_bits_length() -> None:
    assert len(new_empty_bits()) == 36


def test_time_to_index_9_15() -> None:
    """9:15 AM = (9*60+15)/5 = 111."""
    bits = bits_from_windows([("09:15", "09:20")])
    indexes = unpack_indexes(bits)
    assert indexes == [111]


def test_time_to_index_9_00() -> None:
    """9:00 AM = (9*60+0)/5 = 108."""
    bits = bits_from_windows([("09:00", "09:05")])
    indexes = unpack_indexes(bits)
    assert indexes == [108]


def test_idx_to_time_111() -> None:
    """Slot 111 = 555 minutes = 9:15."""
    bits = pack_indexes([111])
    windows = windows_from_bits(bits)
    assert windows == [("09:15:00", "09:20:00")]


def test_full_day_coverage() -> None:
    """00:00-24:00 should yield 288 set bits."""
    bits = bits_from_windows([("00:00", "24:00")])
    assert len(unpack_indexes(bits)) == 288


def test_30_min_window_yields_6_slots() -> None:
    """A 30-min window at 5-min resolution = 6 consecutive slots."""
    bits = bits_from_windows([("09:00", "09:30")])
    indexes = unpack_indexes(bits)
    assert indexes == [108, 109, 110, 111, 112, 113]


def test_toggle_index_288_raises() -> None:
    """Index 288 should raise (out of range)."""
    with pytest.raises(ValueError, match="index out of range"):
        toggle_index(new_empty_bits(), idx=288, value=True)


def test_toggle_index_sets_selected_slot_when_enabled() -> None:
    bits = toggle_index(new_empty_bits(), idx=5, value=True)

    assert unpack_indexes(bits) == [5]


def test_unpack_wrong_length_raises() -> None:
    with pytest.raises(ValueError, match="bits length must be 36"):
        unpack_indexes(b"\x00" * 6)


def test_toggle_wrong_length_raises() -> None:
    with pytest.raises(ValueError, match="bits length must be 36"):
        toggle_index(b"\x00" * 6, idx=0, value=True)


def test_midnight_end_window() -> None:
    """20:00-00:00 should cover slots 240-287 (48 slots)."""
    bits = bits_from_windows([("20:00", "00:00")])
    indexes = unpack_indexes(bits)
    assert len(indexes) == 48
    assert indexes[0] == 240
    assert indexes[-1] == 287


def test_round_trip() -> None:
    original = [("08:00", "12:00"), ("14:30", "17:45")]
    bits = bits_from_windows(original)
    result = windows_from_bits(bits)
    assert result == [("08:00:00", "12:00:00"), ("14:30:00", "17:45:00")]


def test_unpack_indexes_ignores_padding_bits_when_storage_has_extra_byte(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.utils.bitset.BYTES_PER_DAY", BYTES_PER_DAY + 1)
    bits = bytearray(BYTES_PER_DAY + 1)
    bits[-2] = 0x80  # slot 287
    bits[-1] = 0xFF  # simulated padding beyond the last valid slot

    assert unpack_indexes(bytes(bits)) == [SLOTS_PER_DAY - 1]
