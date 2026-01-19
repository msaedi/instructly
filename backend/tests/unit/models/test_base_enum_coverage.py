from __future__ import annotations

from enum import Enum

import pytest

from app.models import base_enum


class GoodEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class BadEnum(Enum):
    ACTIVE = "active"


class BadValueEnum(str, Enum):
    ACTIVE = 1  # type: ignore[assignment]


def test_get_enum_values() -> None:
    assert base_enum._get_enum_values(GoodEnum) == ["active", "inactive"]


def test_create_safe_enum_uses_values() -> None:
    enum_type = base_enum.create_safe_enum(GoodEnum, "good_enum")
    assert "active" in enum_type.enums
    assert "inactive" in enum_type.enums


def test_verify_enum_consistency_bad_enum() -> None:
    with pytest.raises(AssertionError):
        base_enum.verify_enum_consistency(BadEnum)


def test_verify_enum_consistency_bad_value() -> None:
    base_enum.verify_enum_consistency(BadValueEnum)
    assert isinstance(BadValueEnum.ACTIVE.value, str)
