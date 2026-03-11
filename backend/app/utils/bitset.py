from __future__ import annotations

from typing import List, Tuple

from app.core.constants import (
    BYTES_PER_DAY as BYTES_PER_DAY,
    MINUTES_PER_SLOT as MINUTES_PER_SLOT,
    SLOTS_PER_DAY as SLOTS_PER_DAY,
)


def new_empty_bits() -> bytes:
    return bytes(BYTES_PER_DAY)


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
