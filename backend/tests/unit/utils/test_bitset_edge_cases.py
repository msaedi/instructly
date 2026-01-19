import pytest

from app.utils.bitset import (
    bits_from_windows,
    new_empty_bits,
    pack_indexes,
    toggle_index,
    unpack_indexes,
)


def test_pack_indexes_invalid_index_raises() -> None:
    with pytest.raises(ValueError, match="index out of range"):
        pack_indexes([-1])


def test_unpack_indexes_invalid_length_raises() -> None:
    with pytest.raises(ValueError, match="bits length must be 6"):
        unpack_indexes(b"\x00" * 5)


def test_toggle_index_invalid_length_raises() -> None:
    with pytest.raises(ValueError, match="bits length must be 6"):
        toggle_index(b"\x00" * 5, idx=0, value=True)


def test_toggle_index_invalid_index_raises() -> None:
    with pytest.raises(ValueError, match="index out of range"):
        toggle_index(new_empty_bits(), idx=48, value=True)


def test_toggle_index_clears_bit() -> None:
    bits = pack_indexes([3])
    cleared = toggle_index(bits, idx=3, value=False)
    assert unpack_indexes(cleared) == []


def test_bits_from_windows_invalid_format_raises() -> None:
    with pytest.raises(ValueError, match="invalid time format"):
        bits_from_windows([("bad", "01:00")])


def test_bits_from_windows_out_of_bounds_raises() -> None:
    with pytest.raises(ValueError, match="window out of bounds"):
        bits_from_windows([("23:30", "25:00")])
