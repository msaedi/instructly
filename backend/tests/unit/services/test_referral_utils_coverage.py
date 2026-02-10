from __future__ import annotations

import pytest

from app.services import referral_utils


def test_gen_code_raises_for_non_positive_length() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        referral_utils.gen_code(0)


def test_gen_code_uses_expected_length_and_alphabet() -> None:
    code = referral_utils.gen_code(12)

    assert len(code) == 12
    assert set(code).issubset(set(referral_utils.ALPHABET))
