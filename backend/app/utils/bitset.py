from __future__ import annotations

from typing import List, Tuple

from app.core.constants import (
    BITS_PER_TAG as BITS_PER_TAG,
    BYTES_PER_DAY as BYTES_PER_DAY,
    MINUTES_PER_SLOT as MINUTES_PER_SLOT,
    SLOTS_PER_DAY as SLOTS_PER_DAY,
    TAG_BYTES_PER_DAY as TAG_BYTES_PER_DAY,
    TAG_NO_TRAVEL as TAG_NO_TRAVEL,
    TAG_NONE as TAG_NONE,
    TAG_ONLINE_ONLY as TAG_ONLINE_ONLY,
    TAG_RESERVED as TAG_RESERVED,
)


def new_empty_bits() -> bytes:
    return bytes(BYTES_PER_DAY)


def new_empty_tags() -> bytes:
    return bytes(TAG_BYTES_PER_DAY)


def pack_indexes(indexes: List[int]) -> bytes:
    b = bytearray(BYTES_PER_DAY)
    for idx in indexes:
        if not (0 <= idx < SLOTS_PER_DAY):
            raise ValueError(f"index out of range: {idx}")
        byte_i = idx // 8
        bit_i = idx % 8
        b[byte_i] |= 1 << bit_i
    return bytes(b)


def unpack_indexes(bits: bytes) -> List[int]:
    if len(bits) != BYTES_PER_DAY:
        raise ValueError(f"bits length must be {BYTES_PER_DAY}")
    out: List[int] = []
    for byte_i, val in enumerate(bits):
        for bit_i in range(8):
            idx = byte_i * 8 + bit_i
            if idx >= SLOTS_PER_DAY:
                break
            if (val >> bit_i) & 1:
                out.append(idx)
    return out


def toggle_index(bits: bytes, idx: int, value: bool) -> bytes:
    if len(bits) != BYTES_PER_DAY:
        raise ValueError(f"bits length must be {BYTES_PER_DAY}")
    if not (0 <= idx < SLOTS_PER_DAY):
        raise ValueError("index out of range")
    b = bytearray(bits)
    byte_i = idx // 8
    bit_i = idx % 8
    if value:
        b[byte_i] |= 1 << bit_i
    else:
        b[byte_i] &= ~(1 << bit_i)
    return bytes(b)


def get_slot_tag(tags: bytes, slot: int) -> int:
    if len(tags) != TAG_BYTES_PER_DAY:
        raise ValueError(f"tags length must be {TAG_BYTES_PER_DAY}")
    if not (0 <= slot < SLOTS_PER_DAY):
        raise ValueError("slot out of range")
    bit_offset = slot * BITS_PER_TAG
    byte_idx = bit_offset // 8
    bit_pos = bit_offset % 8
    return (tags[byte_idx] >> bit_pos) & 0b11


def set_slot_tag(tags: bytes, slot: int, tag: int) -> bytes:
    if len(tags) != TAG_BYTES_PER_DAY:
        raise ValueError(f"tags length must be {TAG_BYTES_PER_DAY}")
    if not (0 <= slot < SLOTS_PER_DAY):
        raise ValueError("slot out of range")
    if not (TAG_NONE <= tag <= TAG_RESERVED):
        raise ValueError("tag must be 0-3")
    bit_offset = slot * BITS_PER_TAG
    byte_idx = bit_offset // 8
    bit_pos = bit_offset % 8
    b = bytearray(tags)
    b[byte_idx] &= ~(0b11 << bit_pos)
    b[byte_idx] |= (tag & 0b11) << bit_pos
    return bytes(b)


def set_range_tag(tags: bytes, start_slot: int, count: int, tag: int) -> bytes:
    if len(tags) != TAG_BYTES_PER_DAY:
        raise ValueError(f"tags length must be {TAG_BYTES_PER_DAY}")
    if count <= 0:
        raise ValueError("count must be greater than 0")
    if start_slot < 0 or start_slot + count > SLOTS_PER_DAY:
        raise ValueError("range out of bounds")
    if not (TAG_NONE <= tag <= TAG_RESERVED):
        raise ValueError("tag must be 0-3")
    result = bytearray(tags)
    for i in range(count):
        slot = start_slot + i
        bit_offset = slot * BITS_PER_TAG
        byte_idx = bit_offset // 8
        bit_pos = bit_offset % 8
        result[byte_idx] &= ~(0b11 << bit_pos)
        result[byte_idx] |= (tag & 0b11) << bit_pos
    return bytes(result)


def get_range_tag(tags: bytes, start_slot: int, count: int) -> int | None:
    if count <= 0:
        raise ValueError("count must be greater than 0")
    first = get_slot_tag(tags, start_slot)
    for i in range(1, count):
        if get_slot_tag(tags, start_slot + i) != first:
            return None
    return first


def is_tag_compatible(tag: int, location_type: str) -> bool:
    if tag == TAG_NONE:
        return True
    if tag == TAG_ONLINE_ONLY:
        return location_type == "online"
    if tag == TAG_NO_TRAVEL:
        return location_type in {"online", "instructor_location"}
    return False  # TAG_RESERVED (3) intentionally blocks all formats


def windows_from_bits(bits: bytes) -> List[Tuple[str, str]]:
    """Return merged windows as ('HH:MM:SS','HH:MM:SS') tuples."""
    idxs = unpack_indexes(bits)
    if not idxs:
        return []
    windows: List[Tuple[int, int]] = []
    start = prev = idxs[0]
    for idx in idxs[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        windows.append((start, prev + 1))
        start = prev = idx
    windows.append((start, prev + 1))

    def idx_to_time(i: int) -> str:
        minutes = i * MINUTES_PER_SLOT
        hh = minutes // 60
        mm = minutes % 60
        return f"{hh:02d}:{mm:02d}:00"

    return [(idx_to_time(s), idx_to_time(e)) for s, e in windows]


def bits_from_windows(windows: List[Tuple[str, str]]) -> bytes:
    """Inverse of windows_from_bits for 'HH:MM[:SS]' strings."""

    def time_to_index(t: str, *, is_end: bool = False) -> int:
        parts = t.split(":")
        if len(parts) < 2:
            raise ValueError(f"invalid time format: {t}")
        hh, mm = int(parts[0]), int(parts[1])
        if is_end and hh == 0 and mm == 0:
            return SLOTS_PER_DAY
        return (hh * 60 + mm) // MINUTES_PER_SLOT

    idxs: List[int] = []
    for start, end in windows:
        s = time_to_index(start)
        e = time_to_index(end, is_end=True)
        if not (0 <= s <= e <= SLOTS_PER_DAY):
            raise ValueError(f"window out of bounds: {start}-{end}")
        idxs.extend(range(s, e))
    return pack_indexes(idxs)
