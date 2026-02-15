from __future__ import annotations

import pytest

from app.utils.token_utils import parse_token_iat


@pytest.mark.parametrize(
    ("iat_value", "expected"),
    [
        (123, 123),
        (123.9, 123),
        ("456", 456),
        ("bad", None),
        (None, None),
    ],
)
def test_parse_token_iat_variants(iat_value, expected):
    assert parse_token_iat({"iat": iat_value}) == expected


def test_parse_token_iat_missing_claim():
    assert parse_token_iat({}) is None
