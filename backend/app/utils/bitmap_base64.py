from __future__ import annotations

import base64


def encode_bitmap_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_bitmap_bytes(value: str, expected_length: int) -> bytes:
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:  # pragma: no cover - defensive base64 validation
        raise ValueError("invalid base64 bitmap") from exc
    if len(decoded) != expected_length:
        raise ValueError(f"decoded bitmap length must be {expected_length}")
    return decoded
